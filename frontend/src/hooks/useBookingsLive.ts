/** Live booking updates via WebSocket.
 *
 * Mount `<BookingsLiveSync />` once (AuthBootstrap). Screens subscribe via
 * `useBookingsRefreshNonce()` and refetch when the nonce bumps.
 */
import { useEffect, useRef } from "react";

import { presentWaitlistPromotion } from "@/src/services/notifications";
import { useAuthStore } from "@/src/store/useAuthStore";
import { useBookingsRefreshStore } from "@/src/store/useBookingsRefreshStore";
import { uuidHex } from "@/src/utils/uuid";

const BASE_URL =
  process.env.EXPO_PUBLIC_API_BASE_URL ??
  process.env.EXPO_PUBLIC_BACKEND_URL ??
  "https://diu-turf.onrender.com";

function toWsUrl(base: string, token: string): string {
  const wsBase = base.replace(/^http/i, "ws").replace(/\/+$/, "");
  return `${wsBase}/api/ws/bookings?token=${encodeURIComponent(token)}`;
}

const REFRESH_EVENTS = new Set([
  "booking.created",
  "booking.cancelled",
  "waitlist.joined",
  "waitlist.promoted",
]);

/** Subscribe to WS-driven refresh signals (no socket connection here). */
export function useBookingsRefreshNonce(): number {
  return useBookingsRefreshStore((s) => s.nonce);
}

/** @deprecated Use useBookingsRefreshNonce — connected is internal only. */
export function useBookingsLive(): { nonce: number } {
  return { nonce: useBookingsRefreshNonce() };
}

/** Single app-wide WebSocket — silent reconnect, no user-facing status. */
export function BookingsLiveSync(): null {
  const token = useAuthStore((s) => s.token);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const userId = useAuthStore((s) => s.user?.user_id);
  const bump = useBookingsRefreshStore((s) => s.bump);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const userIdRef = useRef(userId);
  userIdRef.current = userId;

  useEffect(() => {
    if (!isAuthenticated || !token || !BASE_URL) return;
    let cancelled = false;

    function connect() {
      if (cancelled || !token) return;
      const ws = new WebSocket(toWsUrl(BASE_URL, token));
      wsRef.current = ws;
      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data);
          if (REFRESH_EVENTS.has(data?.type)) {
            bump();
          }
          if (
            data?.type === "waitlist.promoted" &&
            data.user_id &&
            userIdRef.current &&
            uuidHex(data.user_id) === uuidHex(userIdRef.current)
          ) {
            presentWaitlistPromotion().catch(() => undefined);
          }
        } catch {
          /* ignore */
        }
      };
      ws.onclose = () => {
        if (cancelled) return;
        reconnectTimer.current = setTimeout(connect, 2500);
      };
      ws.onerror = () => {
        try { ws.close(); } catch { /* ignore */ }
      };
    }

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (wsRef.current) {
        try { wsRef.current.close(); } catch { /* ignore */ }
      }
      wsRef.current = null;
    };
  }, [isAuthenticated, token, bump]);

  return null;
}
