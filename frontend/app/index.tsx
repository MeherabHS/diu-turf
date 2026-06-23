/** Splash + entry router. Decides where to send the user based on Zustand auth state. */
import { Redirect } from "expo-router";
import React from "react";

import { LoadingScreen } from "@/src/components/LoadingScreen";
import { useAuthStore } from "@/src/store/useAuthStore";
import { getPostLoginRoute } from "@/src/utils/authRouting";

export default function Index() {
  const isLoading = useAuthStore((s) => s.isLoading);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const user = useAuthStore((s) => s.user);

  if (isLoading) {
    return <LoadingScreen testID="splash-screen" />;
  }

  if (!isAuthenticated || !user) {
    return <Redirect href="/(auth)/login" />;
  }

  const next = getPostLoginRoute(user);
  console.log("[ROUTER] next route", next);
  return <Redirect href={next} />;
}

