/** Profile tab — view and edit account details. */
import { zodResolver } from "@hookform/resolvers/zod";
import React, { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";

import { Button } from "@/src/components/Button";
import { Card } from "@/src/components/Card";
import { ProfileFormFields } from "@/src/components/ProfileFormFields";
import { ScreenHeader } from "@/src/components/ScreenHeader";
import { Toast, type ToastMessage } from "@/src/components/Toast";
import { profileSchema, type ProfileFormValues } from "@/src/schemas/profile";
import { useAuthStore } from "@/src/store/useAuthStore";
import { colors, radii, spacing, typography } from "@/src/theme";
import { isAdminRole } from "@/src/utils/roles";
import { displayName } from "@/src/utils/userDisplay";

export default function ProfileScreen() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const updateProfile = useAuthStore((s) => s.updateProfile);
  const insets = useSafeAreaInsets();
  const [toast, setToast] = useState<ToastMessage | null>(null);

  const {
    control,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting, isDirty },
  } = useForm<ProfileFormValues>({
    resolver: zodResolver(profileSchema),
    mode: "onChange",
    defaultValues: {
      name: user?.name ?? "",
      student_id: user?.student_id ?? "",
      department: user?.department ?? "",
      batch: user?.batch ?? "",
      room_number: user?.room_number ?? "",
      hostel_name: user?.hostel_name ?? "",
      phone: user?.phone ?? "",
    },
  });

  useEffect(() => {
    reset({
      name: user?.name ?? "",
      student_id: user?.student_id ?? "",
      department: user?.department ?? "",
      batch: user?.batch ?? "",
      room_number: user?.room_number ?? "",
      hostel_name: user?.hostel_name ?? "",
      phone: user?.phone ?? "",
    });
  }, [user, reset]);

  const onSubmit = async (values: ProfileFormValues) => {
    try {
      await updateProfile({
        name: values.name.trim(),
        student_id: values.student_id.trim(),
        department: values.department.trim(),
        batch: values.batch.trim(),
        room_number: values.room_number?.trim() || null,
        hostel_name: values.hostel_name?.trim() || null,
        phone: values.phone?.trim() || null,
      });
      setToast({ kind: "success", text: "Profile saved" });
    } catch (e) {
      setToast({ kind: "error", text: e instanceof Error ? e.message : "Failed to save profile" });
    }
  };

  return (
    <SafeAreaView style={styles.container} edges={["top"]} testID="profile-screen">
      <Toast message={toast} onHide={() => setToast(null)} />
      <ScreenHeader eyebrow="PROFILE" title="Account" />
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={[styles.scroll, { paddingBottom: insets.bottom + spacing.xxl }]}>
          <Card testID="profile-card">
            <View style={styles.avatar}>
              <Text style={styles.avatarText}>{(displayName(user)?.[0] ?? "?").toUpperCase()}</Text>
            </View>
            <Text style={styles.name} testID="profile-name">{displayName(user)}</Text>
            <Text style={styles.email} testID="profile-email">{user?.email}</Text>
            <View style={[styles.badge, isAdminRole(user?.role) ? styles.badgeAdmin : styles.badgeStudent]}>
              <Text style={styles.badgeText}>{user?.role?.toUpperCase()}</Text>
            </View>
            <Text style={styles.sectionLabel}>Edit profile</Text>
            {user?.email ? (
              <ProfileFormFields control={control} errors={errors} email={user.email} />
            ) : null}
            <View style={{ marginTop: spacing.lg }}>
              <Button
                label="Save changes"
                onPress={handleSubmit(onSubmit)}
                loading={isSubmitting}
                disabled={!isDirty}
                testID="profile-save-button"
              />
            </View>
          </Card>

          <View style={{ marginTop: spacing.xl }}>
            <Button label="Sign out" variant="secondary" onPress={logout} testID="profile-signout-button" />
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  scroll: { paddingHorizontal: spacing.lg, paddingTop: spacing.sm },
  avatar: {
    width: 64, height: 64, borderRadius: 32,
    backgroundColor: colors.primary,
    alignItems: "center", justifyContent: "center",
    marginBottom: spacing.md,
  },
  avatarText: { color: "#FFFFFF", fontSize: 26, fontWeight: "800" },
  name: { ...typography.h3, color: colors.text_primary },
  email: { ...typography.caption, marginTop: spacing.xs },
  badge: {
    alignSelf: "flex-start",
    paddingVertical: 4, paddingHorizontal: 10,
    borderRadius: radii.pill,
    marginTop: spacing.sm,
  },
  badgeStudent: { backgroundColor: colors.surface_secondary },
  badgeAdmin: { backgroundColor: colors.status_available_bg },
  badgeText: { ...typography.label, fontSize: 10, color: colors.text_primary },
  sectionLabel: { ...typography.label, color: colors.text_secondary, marginTop: spacing.lg },
});
