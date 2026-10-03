import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, NetworkError, describeError } from "../../api/errors";
import { advanceMeeting } from "./api";

/**
 * Listening to a meeting without speaking (design §7.14, meeting draft §12).
 *
 * The learner presses 旁听 and the room carries on by itself: this hook keeps asking the server to advance
 * while the transcript grows. The rules it exists to enforce:
 *
 * - **Every advance is measured against a cursor** (`getCursor()` returns the last `seq` the screen has
 *   seen), which is what makes a retried request free: the server returns the turns it already wrote instead
 *   of generating a second round.
 * - **The meeting waits for its own audio.** Hearing the lines is the point of listening; advancing the
 *   transcript past the sound turns the session into speed-reading. After each round the loop lets synthesis
 *   start, then polls until the queue is empty.
 * - **Speaking stops listening.** Taking the floor is the end of listening, and so is opening the microphone
 *   — the screen wires both to `stop()`.
 * - **The budget is the server's.** `advances_remaining` comes back on every response; this hook stops at zero
 *   and says why instead of hammering a 409.
 */

/** Time for the round that just arrived to start being spoken, before the first check. */
const SETTLE_MS = 700;
/** How often to look again while that round is still playing. */
const AUDIO_POLL_MS = 400;
/** With no audio at all (muted, or nothing to say) the meeting still needs a beat between rounds. */
const PAUSE_BETWEEN_ROUNDS_MS = 900;
/** One more go after an upstream failure: measured, an advance ends in a 502 about 1 round in 8. */
const MAX_TRANSIENT_RETRIES = 1;
const TRANSIENT_RETRY_MS = 2000;

export interface MeetingListening {
  listening: boolean;
  /** `null` until the first response: the server owns the number, the client only displays it. */
  advancesRemaining: number | null;
  error: string | null;
  start: () => void;
  stop: () => void;
  toggle: () => void;
}

export function useMeetingListening(params: {
  sessionId: string;
  /** Last `seq` the screen has seen. A function, so the loop never holds a stale number. */
  getCursor: () => number;
  /** Listening only makes sense in a meeting (§7.14). */
  enabled: boolean;
  /** True while the audio for the last round is still playing. */
  isSpeaking: () => boolean;
}): MeetingListening {
  const { sessionId, getCursor, enabled, isSpeaking } = params;
  const queryClient = useQueryClient();
  const [listening, setListening] = useState(false);
  const [advancesRemaining, setAdvancesRemaining] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const listeningRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inFlightRef = useRef(false);
  const transientRetriesRef = useRef(0);
  // `enabled` follows the session's status, so it is false the moment the session ends — read through a
  // ref, because the catch block of an in-flight request must see the value now, not the one it closed over.
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;
  // The two halves of the loop call each other; refs keep each from depending on the other's identity.
  const stepRef = useRef<() => void>(() => undefined);
  const afterRoundRef = useRef<() => void>(() => undefined);

  const stop = useCallback(() => {
    listeningRef.current = false;
    setListening(false);
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  // The screen can unmount mid-round; a stray timer would then advance a session nobody is looking at.
  useEffect(() => stop, [stop]);

  useEffect(() => {
    if (!enabled) stop();
  }, [enabled, stop]);

  const step = useCallback(async () => {
    if (!listeningRef.current || inFlightRef.current) return;
    inFlightRef.current = true;
    try {
      const response = await advanceMeeting(sessionId, getCursor());
      transientRetriesRef.current = 0;
      setAdvancesRemaining(response.advances_remaining);
      // Refetch rather than appending locally: the transcript is server state (§10.2), and the refetch is also
      // what gives the next round its cursor and feeds the auto-play effect.
      await queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
      if (!listeningRef.current) return;
      if (response.advances_remaining <= 0) {
        stop();
        setError("这场会议已经讨论完了。说一句你的看法，或者结束它。");
        return;
      }
      timerRef.current = setTimeout(() => afterRoundRef.current(), SETTLE_MS);
    } catch (caught) {
      // The session ended while this round was in flight — the learner pressed 结束. That is not a failure
      // to report: the room is closed, and the error would surface right on top of their own tap.
      if (!enabledRef.current) return;
      // A 502/504 is the model being unlucky (§13.2), and the server has already spent its own second
      // attempt on it. `after_seq` makes a client-side retry free: it hands back rounds already written, or
      // buys one new one. One more go turns "1 round in 8 dies" into "you almost never see it".
      const transient =
        (caught instanceof ApiError && caught.status >= 500) || caught instanceof NetworkError;
      if (transient && transientRetriesRef.current < MAX_TRANSIENT_RETRIES && listeningRef.current) {
        transientRetriesRef.current += 1;
        timerRef.current = setTimeout(() => stepRef.current(), TRANSIENT_RETRY_MS);
        return;
      }
      stop();
      if (caught instanceof ApiError && caught.code === "advance_limit_reached") {
        setError("你已经在旁边听很久了：说一句，或者结束这场会议。");
      } else {
        setError(describeError(caught));
      }
    } finally {
      inFlightRef.current = false;
    }
  }, [getCursor, queryClient, sessionId, stop]);

  const afterRound = useCallback(() => {
    if (!listeningRef.current) return;
    if (isSpeaking()) {
      // Still talking: come back shortly. This is the loop that keeps the sound ahead of the text.
      timerRef.current = setTimeout(() => afterRoundRef.current(), AUDIO_POLL_MS);
      return;
    }
    timerRef.current = setTimeout(() => stepRef.current(), PAUSE_BETWEEN_ROUNDS_MS);
  }, [isSpeaking]);

  stepRef.current = () => void step();
  afterRoundRef.current = afterRound;

  const start = useCallback(() => {
    if (!enabled || listeningRef.current) return;
    setError(null);
    listeningRef.current = true;
    setListening(true);
    void step();
  }, [enabled, step]);

  const toggle = useCallback(() => {
    if (listeningRef.current) stop();
    else start();
  }, [start, stop]);

  return { listening, advancesRemaining, error, start, stop, toggle };
}
