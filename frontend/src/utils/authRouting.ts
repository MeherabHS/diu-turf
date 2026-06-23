/** Post-login route selection — shared by index splash and auth store navigation. */
import { router } from "expo-router";

import type { User } from "@/src/types";

import { isAdminRole } from "./roles";

export type PostLoginHref =
  | "/(admin)/(tabs)/dashboard"
  | "/(auth)/complete-profile"
  | "/(tabs)";

export function getPostLoginRoute(user: User): PostLoginHref {
  if (!user.profile_completed) {
    return "/(auth)/complete-profile";
  }
  if (isAdminRole(user.role)) {
    return "/(admin)/(tabs)/dashboard";
  }
  return "/(tabs)";
}

export function navigateAfterAuth(user: User): void {
  const next = getPostLoginRoute(user);
  console.log("[ROUTER] next route", next);
  router.replace(next);
}
