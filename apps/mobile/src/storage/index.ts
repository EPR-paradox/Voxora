/**
 * Local, non-sensitive state (design §10.2 `storage/`).
 *
 * Only the pointer to the session in progress lives here: the server owns every piece of practice data,
 * so this is a convenience cache and nothing is lost if it disappears.
 */

import AsyncStorage from "@react-native-async-storage/async-storage";

const LAST_SESSION_KEY = "voxora:lastSessionId";

export async function getLastSessionId(): Promise<string | null> {
  try {
    return await AsyncStorage.getItem(LAST_SESSION_KEY);
  } catch {
    return null;
  }
}

export async function setLastSessionId(sessionId: string): Promise<void> {
  try {
    await AsyncStorage.setItem(LAST_SESSION_KEY, sessionId);
  } catch {
    // Losing the pointer only costs the learner one extra tap; never fail a flow over it.
  }
}

export async function clearLastSessionId(): Promise<void> {
  try {
    await AsyncStorage.removeItem(LAST_SESSION_KEY);
  } catch {
    // ignored on purpose
  }
}
