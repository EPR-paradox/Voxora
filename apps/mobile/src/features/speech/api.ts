import { apiUpload, TRANSCRIPTION_TIMEOUT_MS } from "../../api/client";
import type { TranscriptionResponse } from "../../api/types";

/**
 * Voice input (design §7.11). The clip goes up, text comes back, and nothing about it is stored
 * server-side — the text only becomes durable when the screen sends it as a message.
 */
export interface RecordedClip {
  uri: string;
  durationMs: number;
}

export function transcribeClip(
  clip: RecordedClip,
  options: { language?: string; timeoutMs?: number; signal?: AbortSignal } = {},
): Promise<TranscriptionResponse> {
  const form = new FormData();
  // React Native's FormData accepts this { uri, name, type } shape for a file; `audio/m4a` matches what
  // expo-audio records and what the server's allowlist expects (§7.11 rule 3).
  form.append("audio_file", {
    uri: clip.uri,
    name: "clip.m4a",
    type: "audio/m4a",
  } as unknown as Blob);
  form.append("language", options.language ?? "en");
  form.append("duration_ms", String(Math.round(clip.durationMs)));

  return apiUpload<TranscriptionResponse>("/practice/speech/transcriptions", form, {
    timeoutMs: options.timeoutMs ?? TRANSCRIPTION_TIMEOUT_MS,
    signal: options.signal,
  });
}
