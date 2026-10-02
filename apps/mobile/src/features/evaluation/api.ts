import { apiRequest, MODEL_CALL_TIMEOUT_MS } from "../../api/client";
import type { EvaluationStatusResponse } from "../../api/types";

/**
 * End the session and generate its report.
 *
 * A failed report is **not** an exception: it arrives as `evaluation_status: "failed"` with an
 * `error_code` (§7.8), so the screen renders the failure state from the payload rather than from a
 * caught error. Only transport problems and request errors reach the catch block.
 */
export function finishSession(sessionId: string): Promise<EvaluationStatusResponse> {
  return apiRequest<EvaluationStatusResponse>(`/practice/sessions/${sessionId}/finish`, {
    method: "POST",
    body: { reason: "user_finished" },
    timeoutMs: MODEL_CALL_TIMEOUT_MS,
  });
}

export function getEvaluation(sessionId: string): Promise<EvaluationStatusResponse> {
  return apiRequest<EvaluationStatusResponse>(`/practice/sessions/${sessionId}/evaluation`);
}

export function retryEvaluation(sessionId: string): Promise<EvaluationStatusResponse> {
  return apiRequest<EvaluationStatusResponse>(
    `/practice/sessions/${sessionId}/evaluation/retry`,
    { method: "POST", body: {}, timeoutMs: MODEL_CALL_TIMEOUT_MS },
  );
}
