import { apiRequest, MODEL_CALL_TIMEOUT_MS, newClientMessageId, toQueryString } from "../../api/client";
import type {
  AbandonSessionResponse,
  AdvanceMeetingResponse,
  PracticeSessionCreated,
  PracticeSessionDetail,
  PracticeSessionListResponse,
  SessionStatus,
  SendPracticeMessageResponse,
} from "../../api/types";

export interface SessionHistoryFilters {
  status?: SessionStatus | null;
  limit?: number;
  offset?: number;
}

/** The learner's own history, newest activity first (§7.7). */
export function listSessions(filters: SessionHistoryFilters = {}): Promise<PracticeSessionListResponse> {
  const query = toQueryString({
    status: filters.status,
    limit: filters.limit ?? 20,
    offset: filters.offset ?? 0,
  });
  return apiRequest<PracticeSessionListResponse>(`/practice/sessions${query}`);
}

export function createSession(scenarioId: string): Promise<PracticeSessionCreated> {
  return apiRequest<PracticeSessionCreated>("/practice/sessions", {
    method: "POST",
    body: { scenario_id: scenarioId, input_mode: "text" },
    timeoutMs: MODEL_CALL_TIMEOUT_MS, // the opening line is a model call
  });
}

export function getSession(sessionId: string): Promise<PracticeSessionDetail> {
  return apiRequest<PracticeSessionDetail>(`/practice/sessions/${sessionId}`);
}

/**
 * Close a session nobody spoke in (design §7.15).
 *
 * The way out of a listening-only session: `finish` needs learner turns before it can produce a report,
 * and a learner who only listened has none. Idempotent — closing something already closed returns 200.
 */
export function abandonSession(sessionId: string): Promise<AbandonSessionResponse> {
  return apiRequest<AbandonSessionResponse>(`/practice/sessions/${sessionId}/abandon`, {
    method: "POST",
  });
}

/**
 * One turn. The caller owns `clientMessageId` so a retry after a timeout replays the same key instead of
 * creating a second user message (§7.6, §9.3); `newClientMessageId()` is only for the first attempt.
 */
export function sendMessage(
  sessionId: string,
  content: string,
  clientMessageId: string,
): Promise<SendPracticeMessageResponse> {
  return apiRequest<SendPracticeMessageResponse>(`/practice/sessions/${sessionId}/messages`, {
    method: "POST",
    body: { content, client_message_id: clientMessageId },
    timeoutMs: MODEL_CALL_TIMEOUT_MS,
  });
}

export { newClientMessageId };

/**
 * Let the meeting continue without speaking (design §7.14).
 *
 * `afterSeq` is the display position the client has already seen — the same value twice returns the turns
 * that are already written instead of buying a second round, so a retry after a timeout is safe.
 */
export function advanceMeeting(sessionId: string, afterSeq: number): Promise<AdvanceMeetingResponse> {
  return apiRequest<AdvanceMeetingResponse>(`/practice/sessions/${sessionId}/advance`, {
    method: "POST",
    body: { after_seq: afterSeq },
    timeoutMs: MODEL_CALL_TIMEOUT_MS,
  });
}
