import { Redirect, Stack } from "expo-router";
import React from "react";

import { useAuthStore } from "@/src/store/useAuthStore";
import { isAdminRole } from "@/src/utils/roles";

export default function AdminLayout() {
  const isLoading = useAuthStore((s) => s.isLoading);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const user = useAuthStore((s) => s.user);

  if (isLoading) return null;
  if (!isAuthenticated) return <Redirect href="/(auth)/login" />;
  if (!isAdminRole(user?.role)) return <Redirect href="/(tabs)" />;

  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="(tabs)" />
      <Stack.Screen name="student/[userId]" />
      <Stack.Screen name="slots" />
    </Stack>
  );
}
