import { File } from "expo-file-system";

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
  form.append("audio_file", clipFormPart(clip.uri));
  form.append("language", options.language ?? "en");
  form.append("duration_ms", String(Math.round(clip.durationMs)));

  return apiUpload<TranscriptionResponse>("/practice/speech/transcriptions", form, {
    timeoutMs: options.timeoutMs ?? TRANSCRIPTION_TIMEOUT_MS,
    signal: options.signal,
  });
}

/**
 * One multipart file part, in the only shape Expo's `fetch` understands.
 *
 * The legacy React Native shape (`{ uri, name, type }`) is rejected outright under SDK 57: Expo ships its
 * own fetch, and its multipart writer accepts a part only as a string, a `Blob`, or an object with a
 * `bytes()` method — anything else fails with `Unsupported FormDataPart implementation`. That error
 * surfaces as a network failure, so it reads like "cannot reach the backend" while the backend has not
 * been contacted at all (measured on a real phone: 80 KB clip, correct path, zero requests server-side).
 *
 * `File` from expo-file-system supplies the bytes; `name` and `type` are set here rather than taken from
 * the file because they become the part's `Content-Disposition` and `Content-Type` on the wire, and the
 * server picks its parser off exactly those (§7.11 rule 3).
 */
export function clipFormPart(uri: string): Blob {
  const file = new File(uri);
  const name = uri.split("/").pop() || "clip.m4a";
  return {
    bytes: () => file.bytes(),
    name,
    type: "audio/m4a",
  } as unknown as Blob;
}

/**
 * Turn whatever the recorder hands back into a URI `fetch` can open.
 *
 * expo-audio returns `file:///...` on one platform and a bare `/data/...` path on another; a file part
 * with no scheme is not a URI as far as React Native's networking layer is concerned, and the request
 * dies as "Network request failed" — which the UI can only report as "cannot reach the backend", a lie
 * when the backend was never contacted. `content://` is left alone: the picker's own scheme is valid.
 */
export function normalizeClipUri(uri: string): string {
  const trimmed = uri.trim();
  if (trimmed.includes("://")) return trimmed;
  return `file://${trimmed.startsWith("/") ? "" : "/"}${trimmed}`;
}

/**
 * Size of the recorded clip, or ``null`` when it cannot be read.
 *
 * Recording can end with an empty file (a very short tap, a device that failed to flush): uploading one
 * is a request that can only fail, and its failure would be reported as a network problem.
 */
export function clipSize(uri: string): number | null {
  try {
    const file = new File(uri);
    if (!file.exists) return null;
    return file.info().size ?? null;
  } catch {
    // An unreadable path is not proof the clip is bad — let the upload have its chance.
    return null;
  }
}
