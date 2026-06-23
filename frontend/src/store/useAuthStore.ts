/**
 * Zustand auth store — Phase 4: Google OAuth + PostgreSQL + JWT.
 *
 * State shape:
 *   user            — authenticated user object (null if not logged in)
 *   token           — JWT access_token stored in memory (SecureStore is source of truth)
 *   isAuthenticated — derived: user !== null && token !== null
 *   isLoading       — true during restoreSession() and loginWithGoogle()
 *   error           — last error message (cleared on new action)
 *
 * Actions:
 *   restoreSession()         — on app launch: load JWT → call /me → hydrate state
 *   loginWithGoogle(idToken) — exchange Google ID token for app JWT
 *   logout()                 — call /logout, clear SecureStore + memory
 *   refreshMe()              — re-fetch user from /me (e.g. after profile update)
 *   completeProfile(payload) — submit student_id etc., then refreshMe()
 *   setError(msg)            — set or clear the error field
 *
 * The Google ID token comes from native Google Sign-In on the Login screen.
 * The store never opens a browser — it only exchanges the token with our backend.
 */
import { create } from "zustand";

import { JWT_STORAGE_KEY } from "@/src/constants";
import { authService } from "@/src/services/authService";
import type { ProfilePayload, RegisterPayload, User } from "@/src/types";
import { navigateAfterAuth } from "@/src/utils/authRouting";
import { getFriendlyErrorMessage } from "@/src/utils/errors";
import { clearUserCache } from "@/src/utils/userCache";
import { storage } from "@/src/utils/storage";

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;

  restoreSession: () => Promise<void>;
  loginWithGoogle: (idToken: string) => Promise<void>;
  loginWithPassword: (email: string, password: string) => Promise<void>;
  registerWithPassword: (payload: RegisterPayload) => Promise<void>;
  /** Development-only login bypass. No-ops silently outside dev builds. */
  loginWithDev: (email: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshMe: () => Promise<void>;
  completeProfile: (payload: ProfilePayload) => Promise<void>;
  /** Alias for completeProfile — used by complete-profile.tsx */
  updateProfile: (payload: ProfilePayload) => Promise<void>;
  /** @deprecated use loginWithGoogle instead — kept for router compat */
  login: () => Promise<void>;
  setError: (msg: string | null) => void;
}

async function persistLogin(
  access_token: string,
  user: User,
  source: "dev" | "google" | "password",
): Promise<void> {
  await storage.secureSet(JWT_STORAGE_KEY, access_token);
  console.log("[AUTH_STORE] token saved");
  console.log("[AUTH_STORE] user role", user.role);
  if (source === "dev") {
    console.log("[DEV_LOGIN] success");
  }
  useAuthStore.setState({
    token: access_token,
    user,
    isAuthenticated: true,
    isLoading: false,
    error: null,
  });
  navigateAfterAuth(user);
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  token: null,
  isAuthenticated: false,
  isLoading: true,
  error: null,

  setError: (msg) => set({ error: msg }),

  // ── App launch ─────────────────────────────────────────────────────────────
  // Hardened (Phase 4.1): isLoading is ALWAYS set to false, on every path —
  // success, stale token, network failure, timeout, or SecureStore error.
  // The app can never be stuck on the JS splash because of this function.
  restoreSession: async () => {
    console.log("[BOOT] restoreSession start");
    set({ isLoading: true, error: null });

    // SecureStore failures must not block startup (Rule 5).
    let token = "";
    try {
      token = (await storage.secureGet<string>(JWT_STORAGE_KEY, "")) ?? "";
    } catch (e) {
      console.warn("[BOOT] SecureStore read failed — continuing unauthenticated", e);
      token = "";
    }

    if (!token) {
      console.log("[BOOT] no stored token — routing to login");
      set({ token: null, user: null, isAuthenticated: false, isLoading: false });
      console.log("[BOOT] restoreSession end");
      return;
    }

    // Validate the stored token via /me, but bound it with a short timeout so
    // an unreachable backend cannot hang startup (Rule 2, 3).
    try {
      console.log("[BOOT] refreshMe start (validating stored token)");
      const { user } = await authService.me(5000);
      console.log("[BOOT] refreshMe success — routing authenticated");
      set({ token, user, isAuthenticated: true, isLoading: false });
    } catch (e) {
      // Network/timeout (status 0) → keep token, but show login so the user
      //   isn't stuck; they can retry once the backend is reachable.
      // Auth error (401) → token is stale, clear it.
      const status = (e as { status?: number })?.status;
      if (status === 0) {
        console.warn("[BOOT] backend unreachable during restore — routing to login (token kept)");
      } else {
        console.warn("[BOOT] stored token invalid — clearing");
        try {
          await storage.secureRemove(JWT_STORAGE_KEY);
        } catch {
          /* ignore */
        }
      }
      set({ token: null, user: null, isAuthenticated: false, isLoading: false });
    }
    console.log("[BOOT] restoreSession end");
  },

  // ── Email + password login ─────────────────────────────────────────────────
  loginWithPassword: async (email: string, password: string) => {
    set({ isLoading: true, error: null });
    try {
      const { access_token, user } = await authService.loginWithPassword(email, password);
      await persistLogin(access_token, user, "password");
    } catch (e) {
      const msg = getFriendlyErrorMessage(e, "Invalid email or password.");
      try {
        await storage.secureRemove(JWT_STORAGE_KEY);
      } catch {
        /* ignore */
      }
      set({ token: null, user: null, isAuthenticated: false, isLoading: false, error: msg });
    }
  },

  registerWithPassword: async (payload: RegisterPayload) => {
    set({ isLoading: true, error: null });
    try {
      const { access_token, user } = await authService.register(payload);
      await persistLogin(access_token, user, "password");
    } catch (e) {
      const msg = getFriendlyErrorMessage(e, "Registration failed.");
      try {
        await storage.secureRemove(JWT_STORAGE_KEY);
      } catch {
        /* ignore */
      }
      set({ token: null, user: null, isAuthenticated: false, isLoading: false, error: msg });
      throw e;
    }
  },

  // ── Google Sign-In (UI hidden — kept for future use) ─────────────────────
  loginWithGoogle: async (idToken: string) => {
    console.log("[GOOGLE_AUTH] loginWithGoogle start");
    set({ isLoading: true, error: null });
    try {
      const { access_token, user } = await authService.googleLogin(idToken);
      await persistLogin(access_token, user, "google");
    } catch (e) {
      const msg = getFriendlyErrorMessage(e, "Google sign-in failed");
      console.warn("[GOOGLE_AUTH] loginWithGoogle failed:", msg);
      try {
        await storage.secureRemove(JWT_STORAGE_KEY);
      } catch {
        /* ignore */
      }
      set({ token: null, user: null, isAuthenticated: false, isLoading: false, error: msg });
    }
  },

  // ── Dev login ──────────────────────────────────────────────────────────────
  loginWithDev: async (email: string) => {
    console.log("[DEV] loginWithDev start");
    set({ isLoading: true, error: null });
    try {
      const { access_token, user } = await authService.devLogin(email);
      await persistLogin(access_token, user, "dev");
    } catch (e) {
      const msg = getFriendlyErrorMessage(e, "Unable to connect right now. Please try again.");
      console.warn("[DEV] loginWithDev failed:", msg);
      try {
        await storage.secureRemove(JWT_STORAGE_KEY);
      } catch {
        /* ignore */
      }
      set({ token: null, user: null, isAuthenticated: false, isLoading: false, error: msg });
    }
  },

  // ── Logout ─────────────────────────────────────────────────────────────────
  logout: async () => {
    const userId = get().user?.user_id;
    try {
      await authService.logout();
    } catch {
      // Best-effort server call; client state is the truth.
    }
    await storage.secureRemove(JWT_STORAGE_KEY);
    await clearUserCache(userId);
    set({ token: null, user: null, isAuthenticated: false, isLoading: false, error: null });
  },

  // ── Refresh current user ───────────────────────────────────────────────────
  refreshMe: async () => {
    try {
      const { user } = await authService.me();
      set({ user });
    } catch {
      // If /me fails, assume session is invalid — logout cleanly.
      await get().logout();
    }
  },

  // ── Complete profile ───────────────────────────────────────────────────────
  completeProfile: async (payload: ProfilePayload) => {
    set({ isLoading: true, error: null });
    try {
      await authService.updateProfile(payload);
      await get().refreshMe();
      set({ isLoading: false });
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Profile update failed";
      set({ isLoading: false, error: msg });
      throw e; // re-throw so the form can show the error
    }
  },

  // ── updateProfile alias (used by complete-profile.tsx) ────────────────────
  updateProfile: async (payload: ProfilePayload) => {
    await get().completeProfile(payload);
  },

  // ── Compat stub ────────────────────────────────────────────────────────────
  // The login screen now calls loginWithGoogle(idToken) directly.
  // This stub prevents crashes if any code still calls login().
  login: async () => {
    set({ error: "Use email and password to sign in." });
  },
}));
