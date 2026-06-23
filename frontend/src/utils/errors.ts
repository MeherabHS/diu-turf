/** Map API/network errors to user-friendly copy — never show raw HTTP status text. */
import { ApiError } from "@/src/services/api";

const GENERIC = "Something went wrong. Please try again.";
const NETWORK = "Unable to connect right now. Please try again.";
const OFFLINE = "You're offline or the server is unreachable.";

function isTechnicalMessage(msg: string): boolean {
  return (
    /^request failed \(\d+\)/i.test(msg) ||
    /^request timed out after \d+ms/i.test(msg) ||
    /network error — could not reach/i.test(msg)
  );
}

export function getFriendlyErrorMessage(
  error: unknown,
  fallback: string = GENERIC,
): string {
  if (error instanceof ApiError) {
    if (error.status === 0) {
      if (/timed out/i.test(error.message)) return NETWORK;
      return OFFLINE;
    }

    const detail = error.message.trim();
    const lower = detail.toLowerCase();

    if (lower.includes("already have an active booking")) {
      return "You already have an active booking for this date.";
    }
    if (
      lower.includes("just booked") ||
      lower.includes("no longer available") ||
      lower.includes("booking conflict") ||
      lower.includes("slot is full")
    ) {
      return "This slot was just booked by someone else.";
    }
    if (lower.includes("suspended") || lower.includes("deactivated")) {
      return detail.length < 160 ? detail : GENERIC;
    }
    if (
      error.status === 409 &&
      (lower.includes("already exists") || lower.includes("already registered"))
    ) {
      return "This email or student ID is already registered. Contact admin if this is your ID.";
    }
    if (error.status >= 500 || isTechnicalMessage(detail)) {
      return GENERIC;
    }
    if (detail.startsWith("__http_")) {
      return GENERIC;
    }
    if (detail.length > 0 && detail.length < 160) {
      return detail;
    }
    return fallback;
  }

  if (error instanceof Error) {
    if (/timed out/i.test(error.message)) return NETWORK;
    if (/network error/i.test(error.message)) return OFFLINE;
    if (isTechnicalMessage(error.message)) return fallback;
    if (error.message.length < 160) return error.message;
  }

  return fallback;
}
