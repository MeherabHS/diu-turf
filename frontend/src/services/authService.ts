/**
 * Auth service — thin wrappers around /api/auth/* endpoints.
 */
import { api } from "./api";
import type {
  AuthMeResponse,
  AuthResponse,
  LoginPayload,
  ProfilePayload,
  RegisterPayload,
} from "@/src/types";

export const authService = {
  register: (payload: RegisterPayload) =>
    api.post<AuthResponse>("/api/auth/register", payload),

  loginWithPassword: (email: string, password: string) =>
    api.post<AuthResponse>("/api/auth/login", { email, password } satisfies LoginPayload),

  /**
   * Exchange a Google ID token (from native Google Sign-In) for an app JWT.
   * Kept for future use — UI is hidden for now.
   */
  googleLogin: async (idToken: string) => {
    const response = await api.post<AuthResponse>("/api/auth/google", { id_token: idToken });
    return response;
  },

  /** Development-only login bypass. */
  devLogin: (email: string) =>
    api.post<AuthResponse>("/api/auth/dev-login", { email }),

  /** @param timeoutMs optional override (startup uses a short 5s budget). */
  me: (timeoutMs?: number) =>
    api.get<AuthMeResponse>("/api/auth/me", timeoutMs ? { timeoutMs } : undefined),

  logout: () => api.post<{ ok: boolean }>("/api/auth/logout"),

  updateProfile: (payload: ProfilePayload) =>
    api.put<AuthMeResponse>("/api/users/profile", payload),
};
