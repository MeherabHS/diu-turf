/**
 * Optional Sentry crash reporting — no-op when EXPO_PUBLIC_SENTRY_DSN is unset.
 *
 * Set EXPO_PUBLIC_SENTRY_DEBUG=true to send events from __DEV__ builds (testing).
 */
import * as Sentry from "@sentry/react-native";
import Constants from "expo-constants";

const dsn = process.env.EXPO_PUBLIC_SENTRY_DSN?.trim() ?? "";

let initialized = false;

export function initSentry(): boolean {
  if (initialized || !dsn) {
    return initialized;
  }

  const appVersion = Constants.expoConfig?.version ?? "unknown";
  const slug = Constants.expoConfig?.slug ?? "frontend";

  Sentry.init({
    dsn,
    environment:
      process.env.EXPO_PUBLIC_ENVIRONMENT ?? (__DEV__ ? "development" : "production"),
    release: `${slug}@${appVersion}`,
    enabled: !__DEV__ || process.env.EXPO_PUBLIC_SENTRY_DEBUG === "true",
    tracesSampleRate: 0,
    sendDefaultPii: false,
    beforeSend(event) {
      if (event.user?.email) {
        delete event.user.email;
      }
      if (event.user?.username && event.user.username.includes("@")) {
        delete event.user.username;
      }
      return event;
    },
  });

  initialized = true;
  console.log("[SENTRY] initialized");
  return true;
}

export function isSentryEnabled(): boolean {
  return initialized;
}

export { Sentry };
