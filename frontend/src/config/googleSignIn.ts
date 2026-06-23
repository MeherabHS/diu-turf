import { GoogleSignin } from "@react-native-google-signin/google-signin";

const EXPECTED_WEB_CLIENT_ID =
  "757976966702-mcd4lkrpkn50s28j4h0qpt2rr7ath1ms.apps.googleusercontent.com";

let configured = false;

export function getGoogleWebClientId(): string {
  const fromEnv = process.env.EXPO_PUBLIC_GOOGLE_CLIENT_ID_WEB;

  if (fromEnv && fromEnv.trim().length > 0) {
    return fromEnv.trim();
  }

  return EXPECTED_WEB_CLIENT_ID;
}

export function configureGoogleSignIn(): void {
  const webClientId = getGoogleWebClientId();

  console.log("[GOOGLE_AUTH] WEB CLIENT ID", webClientId);

  if (webClientId !== EXPECTED_WEB_CLIENT_ID) {
    console.warn("[GOOGLE_AUTH] WEB CLIENT ID mismatch", {
      expected: EXPECTED_WEB_CLIENT_ID,
      actual: webClientId,
    });
  }

  GoogleSignin.configure({
    webClientId,
    offlineAccess: false,
  });

  configured = true;
  console.log("[GOOGLE_AUTH] GoogleSignin.configure() applied");
}

export function isGoogleSignInConfigured(): boolean {
  return configured || Boolean(getGoogleWebClientId());
}

export { EXPECTED_WEB_CLIENT_ID };