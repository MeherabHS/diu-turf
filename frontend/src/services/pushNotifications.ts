/**
 * Expo push token registration — sends device token to backend after auth.
 *
 * Best-effort: permission denial or missing projectId never blocks app usage.
 */
import Constants from "expo-constants";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

import { api } from "./api";

export const BOOKING_UPDATES_CHANNEL = "booking-updates";

let _handlerConfigured = false;
let _channelConfigured = false;
let _lastRegisteredToken: string | null = null;

function resolveProjectId(): string | undefined {
  return (
    Constants.easConfig?.projectId ??
    (Constants.expoConfig?.extra as { eas?: { projectId?: string } } | undefined)?.eas?.projectId
  );
}

export function configurePushNotificationHandler(): void {
  if (_handlerConfigured || Platform.OS === "web") return;
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowBanner: true,
      shouldShowList: true,
      shouldPlaySound: true,
      shouldSetBadge: false,
    }),
  });
  _handlerConfigured = true;
}

export async function ensureAndroidNotificationChannel(): Promise<void> {
  if (_channelConfigured || Platform.OS !== "android") return;
  await Notifications.setNotificationChannelAsync(BOOKING_UPDATES_CHANNEL, {
    name: "Booking Updates",
    importance: Notifications.AndroidImportance.HIGH,
    vibrationPattern: [0, 250, 250, 250],
    enableVibrate: true,
  });
  _channelConfigured = true;
}

export async function registerPushNotificationsWithBackend(): Promise<void> {
  if (Platform.OS === "web") return;

  configurePushNotificationHandler();
  await ensureAndroidNotificationChannel();

  const settings = await Notifications.getPermissionsAsync();
  let granted =
    settings.granted ||
    settings.ios?.status === Notifications.IosAuthorizationStatus.PROVISIONAL;

  if (!granted) {
    const req = await Notifications.requestPermissionsAsync();
    granted =
      req.granted ||
      req.ios?.status === Notifications.IosAuthorizationStatus.PROVISIONAL;
  }

  if (!granted) {
    if (__DEV__) console.log("[PUSH] notification permission denied — skipping token registration");
    return;
  }

  const projectId = resolveProjectId();
  if (!projectId) {
    if (__DEV__) {
      console.warn(
        "[PUSH] EAS projectId missing — add extra.eas.projectId to app.json for push tokens",
      );
    }
    return;
  }

  try {
    const tokenResult = await Notifications.getExpoPushTokenAsync({ projectId });
    const expoPushToken = tokenResult.data;
    if (!expoPushToken || expoPushToken === _lastRegisteredToken) {
      if (__DEV__ && expoPushToken) {
        console.log("[PUSH] token unchanged — skip backend sync");
      }
      return;
    }

    await api.post("/api/notifications/push-token", {
      expo_push_token: expoPushToken,
      platform: Platform.OS,
    });
    _lastRegisteredToken = expoPushToken;
    if (__DEV__) {
      console.log("[PUSH] token registered with backend", expoPushToken.slice(0, 28) + "...");
    }
  } catch (e) {
    if (__DEV__) {
      console.warn("[PUSH] token registration failed (non-fatal)", e);
    }
  }
}

export function clearRegisteredPushTokenCache(): void {
  _lastRegisteredToken = null;
}
