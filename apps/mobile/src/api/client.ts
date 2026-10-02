/**
 * The single fetch wrapper (design §10.2: "API client + 配置").
 *
 * Everything the screens need to know about transport lives here: base URL resolution, the timeout that
 * turns a hung request into a retryable state, and the `{ error: { code, message } }` envelope from
 * §7.12 turned into a typed `ApiError`. No screen calls `fetch` directly.
 */

import { Platform } from "react-native";

import { ApiError, NetworkError } from "./errors";
import type { ApiErrorBody } from "./types";

const DEFAULT_TIMEOUT_MS = 30_000;
/**
 * Finishing a session makes one model call server-side and was measured at 13-15s, so it needs a much
 * longer leash than a normal request before the client calls it a failure.
 */
export const MODEL_CALL_TIMEOUT_MS = 120_000;

function defaultBaseUrl(): string {
  const configured = process.env.EXPO_PUBLIC_API_BASE_URL;
  if (configured) return configured.replace(/\/+$/, "");
  // Android emulators reach the host machine through 10.0.2.2; a physical phone needs the LAN address
  // in EXPO_PUBLIC_API_BASE_URL. Loopback is correct for web preview and iOS simulator.
  const host = Platform.OS === "android" ? "10.0.2.2" : "127.0.0.1";
  return `http://${host}:8000/api/v1`;
}

export const API_BASE_URL = defaultBaseUrl();

/**
 * The local API is deliberately token-free for loopback clients but requires a bearer token from
 * anything else (§3.1) — which is exactly what a phone on the LAN is, so this dev token ships inside
 * the build. It is the local-development guard, not user authentication, and must not be reused for a
 * public deployment (see §12).
 */
const ACCESS_TOKEN = process.env.EXPO_PUBLIC_API_ACCESS_TOKEN;

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH";
  body?: unknown;
  timeoutMs?: number;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, timeoutMs = DEFAULT_TIMEOUT_MS } = options;

  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: buildHeaders(body),
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (error) {
    if (timedOut) {
      throw new NetworkError(`请求超过 ${Math.round(timeoutMs / 1000)} 秒没有响应。`, {
        isTimeout: true,
      });
    }
    throw new NetworkError(error instanceof Error ? error.message : "网络请求失败。");
  } finally {
    clearTimeout(timer);
  }

  const raw = await response.text();
  const payload: unknown = raw ? safeJsonParse(raw) : null;

  if (!response.ok) {
    const envelope = (payload as { error?: ApiErrorBody } | null)?.error;
    throw new ApiError({
      status: response.status,
      code: envelope?.code ?? "unknown_error",
      message: envelope?.message ?? `HTTP ${response.status}`,
      requestId: envelope?.request_id ?? response.headers.get("X-Request-ID"),
      details: envelope?.details,
    });
  }

  return payload as T;
}

function buildHeaders(body: unknown): Record<string, string> | undefined {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (ACCESS_TOKEN) headers.Authorization = `Bearer ${ACCESS_TOKEN}`;
  return Object.keys(headers).length > 0 ? headers : undefined;
}

function safeJsonParse(raw: string): unknown {
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

/**
 * Idempotency key for a turn (§7.6). RFC 4122 v4 from Math.random is enough: this value only has to be
 * unique for one learner's retries, it is not a secret and never authenticates anything.
 */
export function newClientMessageId(): string {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (character) => {
    const random = (Math.random() * 16) | 0;
    const value = character === "x" ? random : (random & 0x3) | 0x8;
    return value.toString(16);
  });
}

export function toQueryString(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}
