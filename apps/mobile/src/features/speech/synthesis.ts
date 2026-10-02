import { File, Paths } from "expo-file-system";

import { apiBinary } from "../../api/client";

/**
 * Voice output (design §7.13, meeting-mode §9).
 *
 * The server never keeps the audio, so a player needs it on disk before it can open it: the bytes are
 * written to the app's own cache directory, played, and deleted. That makes the cache a playback
 * buffer, not a copy — nothing survives a line finishing or a learner pressing stop.
 */
export interface SpokenLine {
  /** Playable `file://` URI. */
  uri: string;
  contentType: string;
  /** Kept so the file can be deleted when the line is done with. */
  file: File;
}

let sequence = 0;

export async function synthesizeLine(
  input: { text: string; voice: string },
  options: { signal?: AbortSignal } = {},
): Promise<SpokenLine> {
  const { bytes, contentType } = await apiBinary("/practice/speech/synthesis", {
    body: { text: input.text, voice: input.voice },
    signal: options.signal,
  });

  // The extension follows the content type rather than a hard-coded one: the mock provider answers with
  // a WAV, and a player that gets `.mp3` containing RIFF data can refuse the file.
  const extension = contentType.includes("wav") ? "wav" : "mp3";
  const file = new File(Paths.cache, `voxora-line-${Date.now()}-${sequence++}.${extension}`);
  file.create({ overwrite: true });
  file.write(bytes);
  return { uri: file.uri, contentType, file };
}

/** Best effort: a file that cannot be deleted is the system's problem, not the learner's. */
export function discardLine(line: SpokenLine): void {
  try {
    if (line.file.exists) {
      line.file.delete();
    }
  } catch {
    // Ignore: the cache directory is reclaimed by the OS anyway.
  }
}
