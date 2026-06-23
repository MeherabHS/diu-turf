/** Register Expo push token when the user is authenticated. */
import { useEffect } from "react";

import { registerPushNotificationsWithBackend } from "@/src/services/pushNotifications";

export function useRegisterPushNotifications(isAuthenticated: boolean): void {
  useEffect(() => {
    if (!isAuthenticated) return;
    registerPushNotificationsWithBackend().catch(() => {
      /* best-effort — never block UI */
    });
  }, [isAuthenticated]);
}
