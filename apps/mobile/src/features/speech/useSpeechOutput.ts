import { createAudioPlayer, setAudioModeAsync, type AudioPlayer } from "expo-audio";
import { useCallback, useEffect, useRef, useState } from "react";

import { AbortError } from "../../api/client";
import { describeError } from "../../api/errors";
import { discardLine, synthesizeLine, type SpokenLine } from "./synthesis";

/**
 * Voice output (design §7.13, meeting-mode §9): speak the AI's lines, one after another.
 *
 * The rules that shape this hook:
 *
 * - **One line at a time, in order.** A meeting answers with up to three speakers; playing them over each
 *   other would be noise, so lines queue and play sequentially.
 * - **Opening the mic stops playback** (§9.2). This is not an optimisation: with the speaker still talking
 *   the learner records the AI's voice into their own turn.
 * - **Nothing is cached.** The audio lives on the server for exactly one request, so a replay synthesises
 *   it again (a second or two, free) — the alternative is keeping a copy of every voice the learner has
 *   ever heard.
 * - **A line that cannot be spoken does not block the queue.** Speech is an enhancement; a synthesis
 *   failure must not cost the learner the rest of the reply.
 */

export interface SpeechLine {
  /** Id of the message being spoken, so the bubble can show a playing state. */
  id: string;
  text: string;
  /** From the session's `participants[].voice`; a line without one is skipped. */
  voice: string | null;
}

export interface SpeechOutput {
  /** Id of the message currently being spoken, if any. */
  playingId: string | null;
  /**
   * True from the moment a line starts being synthesised until the queue is empty.
   *
   * The listening loop waits on this: a meeting that keeps advancing while the audio is still on an earlier
   * line reads as a transcript racing its own soundtrack, and in listening mode the sound *is* the content.
   */
  busy: boolean;
  muted: boolean;
  error: string | null;
  setMuted: (muted: boolean) => void;
  /** Queue new lines and start speaking (does nothing while muted). */
  speak: (lines: SpeechLine[]) => void;
  /** Speak one line now, interrupting whatever is playing (manual intent beats the mute switch). */
  replay: (line: SpeechLine) => void;
  /** Stop and drop the queue: the learner is about to speak, or is leaving the page. */
  stop: () => void;
}

export function useSpeechOutput(): SpeechOutput {
  const [playingId, setPlayingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [muted, setMutedState] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const playerRef = useRef<AudioPlayer | null>(null);
  const queueRef = useRef<SpeechLine[]>([]);
  const drainingRef = useRef(false);
  const mutedRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  const currentRef = useRef<{ audio: SpokenLine } | null>(null);
  // Resolves the "wait until this line finishes" promise. Held in a ref so `stop` and unmount can unblock
  // a drain that is sitting on it.
  const finishRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    const player = createAudioPlayer();
    playerRef.current = player;
    const subscription = player.addListener("playbackStatusUpdate", (status) => {
      if (status.didJustFinish) {
        finishRef.current?.();
      }
    });
    return () => {
      subscription.remove();
      finishRef.current?.();
      if (currentRef.current) {
        discardLine(currentRef.current.audio);
        currentRef.current = null;
      }
      try {
        player.remove();
      } catch {
        // Already released.
      }
      playerRef.current = null;
    };
  }, []);

  const playToEnd = useCallback((uri: string) => {
    return new Promise<void>((resolve) => {
      const player = playerRef.current;
      if (!player) {
        resolve();
        return;
      }
      finishRef.current = () => {
        finishRef.current = null;
        resolve();
      };
      player.replace({ uri });
      player.play();
    });
  }, []);

  const drain = useCallback(async () => {
    if (drainingRef.current) return;
    drainingRef.current = true;
    setBusy(true);
    try {
      // Speech, not music: it must be audible with the silent switch on, and it should duck other audio
      // rather than fight it. Failures here (web, odd Android builds) must not stop playback.
      await setAudioModeAsync({ playsInSilentMode: true, interruptionMode: "duckOthers" }).catch(
        () => undefined,
      );
      while (queueRef.current.length > 0 && !mutedRef.current) {
        const line = queueRef.current.shift();
        if (!line?.voice) continue;
        const controller = new AbortController();
        abortRef.current = controller;
        try {
          const audio = await synthesizeLine(
            { text: line.text, voice: line.voice },
            { signal: controller.signal },
          );
          currentRef.current = { audio };
          setPlayingId(line.id);
          await playToEnd(audio.uri);
          discardLine(audio);
          currentRef.current = null;
          setPlayingId(null);
        } catch (caught) {
          if (!(caught instanceof AbortError)) {
            // Enhancement, not a requirement: say nothing and keep the queue moving.
            setError(describeError(caught));
          }
        } finally {
          abortRef.current = null;
        }
      }
    } finally {
      drainingRef.current = false;
      setPlayingId(null);
      setBusy(false);
    }
  }, [playToEnd]);

  const speak = useCallback(
    (lines: SpeechLine[]) => {
      if (mutedRef.current) return;
      const playable = lines.filter((line) => line.voice && line.text.trim());
      if (playable.length === 0) return;
      setError(null);
      queueRef.current.push(...playable);
      void drain();
    },
    [drain],
  );

  const stop = useCallback(() => {
    queueRef.current = [];
    abortRef.current?.abort();
    try {
      playerRef.current?.pause();
    } catch {
      // A player that is already gone is exactly the state we want.
    }
    if (currentRef.current) {
      discardLine(currentRef.current.audio);
      currentRef.current = null;
    }
    setPlayingId(null);
    finishRef.current?.();
  }, []);

  const replay = useCallback(
    (line: SpeechLine) => {
      stop();
      if (!line.voice) return;
      queueRef.current.push(line);
      void drain();
    },
    [drain, stop],
  );

  const setMuted = useCallback(
    (next: boolean) => {
      mutedRef.current = next;
      setMutedState(next);
      if (next) stop();
    },
    [stop],
  );

  return { playingId, busy, muted, error, setMuted, speak, replay, stop };
}
