import {
  RecordingPresets,
  requestRecordingPermissionsAsync,
  useAudioRecorder,
  useAudioRecorderState,
} from "expo-audio";
import { useCallback, useEffect, useRef, useState } from "react";

import { AbortError } from "../../api/client";
import { describeError } from "../../api/errors";
import { transcribeClip, type RecordedClip } from "./api";

/**
 * The mic on/off toggle from design §10.4, as a hook.
 *
 * The screen decides what to do with the text (fill the box for a single-character practice, send it
 * straight away in a meeting); this hook only gets a clip turned into text, and keeps the state that the
 * design requires to be visible:
 *
 * - a hard 300 s ceiling, with the last 30 s flagged so a sentence is not cut off mid-word,
 * - a system interruption (backgrounding, a call, audio focus stolen) ends the recording and transcribes
 *   what was captured instead of throwing it away,
 * - a failed transcription keeps the clip so "retry" re-uploads the same audio instead of asking the
 *   learner to say it again,
 * - a denied permission falls back to typing for the rest of the session rather than re-prompting.
 */

/** §7.11 rule 3: the server refuses longer clips, so the client never records one. */
export const MAX_RECORDING_MS = 300_000;
const WARN_BEFORE_END_MS = 30_000;

export type VoicePhase = "idle" | "recording" | "transcribing";

export interface VoiceInput {
  phase: VoicePhase;
  /** 0-1, for the level meter; the design wants a visible sign that the mic is live. */
  level: number;
  elapsedMs: number;
  /** True for the last 30 s of the ceiling. */
  endingSoon: boolean;
  error: string | null;
  permissionDenied: boolean;
  toggle: () => void;
  retry: () => void;
  cancel: () => void;
  onText: (text: string) => void;
}

export function useVoiceInput(onText: (text: string) => void): VoiceInput {
  // The SDK's own status listener is what tells us a recording ended without the learner asking: a call,
  // the app going to the background, or audio focus being taken by another app. Declared through a ref
  // because `finish` is defined below and the listener must not be re-registered on every render.
  const finishRef = useRef<(() => Promise<void>) | null>(null);
  const recorder = useAudioRecorder(
    { ...RecordingPresets.HIGH_QUALITY, isMeteringEnabled: true },
    (recordingStatus) => {
      if (recordingStatus.isFinished && phaseRef.current === "recording") {
        void finishRef.current?.();
      }
    },
  );
  const status = useAudioRecorderState(recorder, 100);

  const [phase, setPhase] = useState<VoicePhase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [failedClip, setFailedClip] = useState<RecordedClip | null>(null);

  // Refs, not state: the recorder's status callback and the auto-stop effect must see the current phase
  // without re-subscribing on every render.
  const phaseRef = useRef<VoicePhase>("idle");
  const startedAtRef = useRef(0);
  const transcribingRef = useRef(false);
  const uploadAbortRef = useRef<AbortController | null>(null);
  const onTextRef = useRef(onText);
  onTextRef.current = onText;

  const setPhaseBoth = useCallback((next: VoicePhase) => {
    phaseRef.current = next;
    setPhase(next);
  }, []);

  const upload = useCallback(
    async (clip: RecordedClip) => {
      if (transcribingRef.current) return;
      transcribingRef.current = true;
      const controller = new AbortController();
      uploadAbortRef.current = controller;
      setPhaseBoth("transcribing");
      setError(null);
      try {
        const result = await transcribeClip(clip, { signal: controller.signal });
        setFailedClip(null);
        onTextRef.current(result.text);
      } catch (caught) {
        if (caught instanceof AbortError) {
          // The learner cancelled: not an error, and not something to offer a retry for.
          setFailedClip(null);
        } else {
          // Keep the clip: §10.4 wants "重试" to re-upload the same audio, not a new take.
          setFailedClip(clip);
          setError(describeError(caught));
        }
      } finally {
        uploadAbortRef.current = null;
        transcribingRef.current = false;
        setPhaseBoth("idle");
      }
    },
    [setPhaseBoth],
  );

  const finish = useCallback(async () => {
    if (phaseRef.current !== "recording") return;
    const elapsed = status.durationMillis || Date.now() - startedAtRef.current;
    let uri = recorder.uri ?? status.url;
    setPhaseBoth("transcribing"); // set first: stopping is async and must not race the toggle
    try {
      await recorder.stop();
      uri = recorder.uri ?? uri;
    } catch (caught) {
      setPhaseBoth("idle");
      setError(describeError(caught));
      return;
    }
    if (!uri) {
      setPhaseBoth("idle");
      setError("没有拿到录音文件，请再试一次。");
      return;
    }
    await upload({ uri, durationMs: elapsed });
  }, [recorder, setPhaseBoth, status.durationMillis, status.url, upload]);

  finishRef.current = finish;

  // Hard ceiling (§10.4): forgetting to close the mic is the failure mode a toggle introduces.
  useEffect(() => {
    if (phase !== "recording") return;
    const timer = setInterval(() => {
      if (Date.now() - startedAtRef.current >= MAX_RECORDING_MS) {
        void finish();
      }
    }, 500);
    return () => clearInterval(timer);
  }, [finish, phase]);

  const start = useCallback(async () => {
    setError(null);
    try {
      const permission = await requestRecordingPermissionsAsync();
      if (!permission.granted) {
        setPermissionDenied(true);
        return;
      }
      await recorder.prepareToRecordAsync();
      recorder.record();
      startedAtRef.current = Date.now();
      setPhaseBoth("recording");
    } catch (caught) {
      setPhaseBoth("idle");
      setError(describeError(caught));
    }
  }, [recorder, setPhaseBoth]);

  const cancel = useCallback(() => {
    if (phaseRef.current === "recording") {
      void recorder.stop().catch(() => undefined);
      setPhaseBoth("idle");
    }
    // Cancelling an upload must actually stop it (§10.4), not just hide the spinner.
    uploadAbortRef.current?.abort();
    setFailedClip(null);
    setError(null);
  }, [recorder, setPhaseBoth]);

  const toggle = useCallback(() => {
    if (phaseRef.current === "recording") {
      void finish();
      return;
    }
    if (phaseRef.current === "transcribing") return;
    void start();
  }, [finish, start]);

  const retry = useCallback(() => {
    if (failedClip) void upload(failedClip);
  }, [failedClip, upload]);

  const elapsedMs = phase === "recording" ? status.durationMillis : 0;
  return {
    phase,
    level: levelFromMetering(status.metering),
    elapsedMs,
    endingSoon: phase === "recording" && elapsedMs >= MAX_RECORDING_MS - WARN_BEFORE_END_MS,
    error,
    permissionDenied,
    toggle,
    retry,
    cancel,
    onText,
  };
}

/**
 * Metering arrives in dBFS (about -160..0). Anything below -50 dB is room noise and would leave the bar
 * looking dead, so the visible range starts there.
 */
function levelFromMetering(metering: number | undefined): number {
  if (metering === undefined || Number.isNaN(metering)) return 0;
  const floor = -50;
  const clamped = Math.min(Math.max(metering, floor), 0);
  return (clamped - floor) / -floor;
}

export function formatDuration(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}
