/**
 * Root layout — startup hardened (Phase 4.1).
 *
 * ROOT CAUSE of the previous splash freeze:
 *   The old code did `if (!loaded && !error) return null;` where `loaded`
 *   came from useIconFonts() which, under Expo Go, fetches ~19 .ttf files
 *   from a remote CDN (jsdelivr). On the Android emulator, if that CDN fetch
 *   stalls (slow/no network, blocked host), useFonts never resolves to
 *   `true` and never errors → the layout returned null forever → the React
 *   tree never mounted → SplashScreen.hideAsync() (gated on loaded||error)
 *   never ran → the native "frontend" splash stayed up permanently.
 *
 * FIX (Rule 1, 2, 6): startup can NEVER hang on fonts.
 *   - A hard 3s timeout forces the app to render regardless of font state.
 *   - The splash is always hidden once we decide to render.
 *   - Missing/slow icon fonts only cause "tofu" glyphs, never a freeze.
 */
import { Stack } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import { useEffect, useState } from "react";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { useIconFonts } from "@/src/hooks/use-icon-fonts";
import { initSentry, Sentry } from "@/src/config/sentry";
import { AuthBootstrap } from "@/src/store/AuthBootstrap";

initSentry();

// Maximum time we will hold the splash for font loading before giving up.
const STARTUP_FONT_TIMEOUT_MS = 3000;

SplashScreen.preventAutoHideAsync().catch(() => {
  /* preventAutoHide can reject if called twice — harmless */
});

export default Sentry.wrap(RootLayout);

function RootLayout() {
  const [loaded, error] = useIconFonts();
  const [fontTimedOut, setFontTimedOut] = useState(false);

  console.log("[BOOT] App launched");

  // Hard timeout: never wait on fonts longer than STARTUP_FONT_TIMEOUT_MS.
  useEffect(() => {
    const id = setTimeout(() => {
      console.log("[BOOT] font load timed out — rendering anyway");
      setFontTimedOut(true);
    }, STARTUP_FONT_TIMEOUT_MS);
    return () => clearTimeout(id);
  }, []);

  const ready = loaded || !!error || fontTimedOut;

  // Hide the native splash as soon as we are ready to render anything.
  useEffect(() => {
    if (ready) {
      console.log("[BOOT] hiding splash (loaded=%s, error=%s, timedOut=%s)", loaded, !!error, fontTimedOut);
      SplashScreen.hideAsync().catch(() => {
        /* already hidden — harmless */
      });
    }
  }, [ready, loaded, error, fontTimedOut]);

  // Only the native splash shows during this brief window (≤ 3s).
  if (!ready) return null;

  return (
    <SafeAreaProvider>
      <AuthBootstrap>
        <StatusBar style="dark" />
        <Stack
          screenOptions={{ headerShown: false, contentStyle: { backgroundColor: "#FFFFFF" } }}
        />
      </AuthBootstrap>
    </SafeAreaProvider>
  );
}
