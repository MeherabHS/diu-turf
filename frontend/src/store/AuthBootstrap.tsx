/**
 * AuthBootstrap — runs session restore on app start.
 *
 * Phase 2 status:
 *   - Emergent deep-link session_id listener removed.
 *   - expo-linking dependency removed from this file.
 *   - Only action: call restoreSession() once on mount, which reads the
 *     persisted JWT and calls /api/auth/me.
 *
 * TODO(phase4): After email/password auth lands, no changes needed here —
 *   restoreSession() will continue to work via the same JWT/storage mechanism.
 */
import React, { useEffect } from "react";

import { BookingsLiveSync } from "@/src/hooks/useBookingsLive";
import { useRegisterPushNotifications } from "@/src/hooks/useRegisterPushNotifications";
import { useAuthStore } from "@/src/store/useAuthStore";

export const AuthBootstrap: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const restoreSession = useAuthStore((s) => s.restoreSession);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  useRegisterPushNotifications(isAuthenticated);

  useEffect(() => {
    console.log("[BOOT] AuthBootstrap mounted");
    restoreSession();
  }, [restoreSession]);

  return (
    <>
      {isAuthenticated ? <BookingsLiveSync /> : null}
      {children}
    </>
  );
};
