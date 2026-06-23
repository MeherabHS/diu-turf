/** Thin fetch wrapper that injects the JWT and base URL.
 *
 * Phase 4.1 hardening:
 *   - Every request has an AbortController timeout (default 8s) so a dead
 *     backend can NEVER hang a screen indefinitely (Rule 2).
 *   - Network/timeout failures throw a typed ApiError(0, ...) the caller can
 *     handle gracefully (e.g. fall back to the login screen — Rule 3).
 *   - BASE_URL diagnostics warn when localhost is used on a native target
 *     (Android emulator must use 10.0.2.2, not localhost).
 */
import { Platform } from "react-native";

import { JWT_STORAGE_KEY } from "@/src/constants";
import { storage } from "@/src/utils/storage";

// EXPO_PUBLIC_API_BASE_URL is canonical (Phase 4+); old name kept as fallback.
const BASE_URL =
  process.env.EXPO_PUBLIC_API_BASE_URL ||
  process.env.EXPO_PUBLIC_BACKEND_URL ||
  "https://diu-turf.onrender.com";

// Default per-request timeout. Startup calls override this with a shorter one.
const DEFAULT_TIMEOUT_MS = 8000;

// Diagnostic: localhost on a native device/emulator will silently fail.
if (
  Platform.OS !== "web" &&
  /localhost|127\.0\.0\.1/.test(BASE_URL)
) {
  console.warn(
    "[API] EXPO_PUBLIC_API_BASE_URL points at localhost on a native target. " +
    "Android emulator must use http://10.0.2.2:8001. Current: " + BASE_URL,
  );
}
if (!BASE_URL) {
  console.warn("[API] EXPO_PUBLIC_API_BASE_URL is empty — API calls will fail. Check your .env.");
}

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, body: unknown, message: string) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

async function buildHeaders(): Promise<Record<string, string>> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };
  const token = await storage.secureGet<string>(JWT_STORAGE_KEY, "");
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

interface RequestOptions {
  timeoutMs?: number;
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  opts: RequestOptions = {},
): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  let res: Response;
  try {
    res = await fetch(url, {
      method,
      headers: await buildHeaders(),
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
  } catch (e) {
    clearTimeout(timeoutId);
    // AbortError (timeout) or network failure → typed error, status 0.
    const aborted = e instanceof Error && e.name === "AbortError";
    const message = aborted
      ? `Request timed out after ${timeoutMs}ms`
      : "Network error — could not reach the server";
    console.warn("[API] %s %s failed: %s", method, path, message);
    throw new ApiError(0, null, message);
  } finally {
    clearTimeout(timeoutId);
  }

  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!res.ok) {
    const rawDetail =
      data && typeof data === "object" && "detail" in (data as Record<string, unknown>)
        ? String((data as Record<string, unknown>).detail)
        : "";
    throw new ApiError(res.status, data, rawDetail || `__http_${res.status}__`);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, opts?: RequestOptions) => request<T>("GET", path, undefined, opts),
  post: <T>(path: string, body?: unknown, opts?: RequestOptions) => request<T>("POST", path, body, opts),
  put: <T>(path: string, body?: unknown, opts?: RequestOptions) => request<T>("PUT", path, body, opts),
  patch: <T>(path: string, body?: unknown, opts?: RequestOptions) => request<T>("PATCH", path, body, opts),
  del: <T>(path: string, opts?: RequestOptions) => request<T>("DELETE", path, undefined, opts),
};
