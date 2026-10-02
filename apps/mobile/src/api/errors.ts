/**
 * Error types the UI branches on.
 *
 * The backend already tells the difference between "the request was wrong" and "the model failed"
 * through `error.code` (design §7.12), so the client keeps that code instead of flattening everything
 * into one message. Screens only need `isRetryable` for the decision that matters: show a retry button
 * or not.
 */

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly details: Record<string, unknown>;

  constructor(params: {
    status: number;
    code: string;
    message: string;
    requestId?: string | null;
    details?: Record<string, unknown>;
  }) {
    super(params.message);
    this.name = "ApiError";
    this.status = params.status;
    this.code = params.code;
    this.requestId = params.requestId ?? null;
    this.details = params.details ?? {};
  }

  get isRetryable(): boolean {
    // 409 turn_in_progress means another turn is still generating: waiting and retrying is correct.
    // 4xx otherwise means the request itself is wrong, so retrying the same body changes nothing.
    if (this.status >= 500) return true;
    return this.code === "turn_in_progress";
  }
}

/** The request never reached the server, or the connection dropped mid-flight. */
export class NetworkError extends Error {
  readonly isTimeout: boolean;

  constructor(message: string, options: { isTimeout?: boolean } = {}) {
    super(message);
    this.name = "NetworkError";
    this.isTimeout = options.isTimeout ?? false;
  }

  get isRetryable(): boolean {
    return true;
  }
}

export function isApiError(error: unknown, code?: string): error is ApiError {
  if (!(error instanceof ApiError)) return false;
  return code === undefined || error.code === code;
}

export function isRetryable(error: unknown): boolean {
  if (error instanceof ApiError || error instanceof NetworkError) return error.isRetryable;
  return false;
}

/** Human-readable message for anything thrown by the api layer. */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.code) {
      case "turn_in_progress":
        return "上一条还在生成，稍等一下再发。";
      case "session_not_active":
        return "这次练习已经结束了。";
      case "session_has_no_user_turns":
        return "还没有你的发言，没有什么可以评价。";
      case "evaluation_not_found":
        return "这次练习还没有生成评价。";
      case "evaluation_in_progress":
        return "评价正在生成中。";
      case "resource_not_found":
        return "找不到这个资源。";
      case "service_unavailable":
        return "服务暂时不可用，检查一下数据库。";
      default:
        return error.message;
    }
  }
  if (error instanceof NetworkError) {
    return error.isTimeout ? "请求超时，可以重试。" : "连不上后端，检查网络或服务是否在跑。";
  }
  if (error instanceof Error) return error.message;
  return "未知错误。";
}
