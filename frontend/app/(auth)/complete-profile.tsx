/** Profile completion screen — React Hook Form + Zod validation. */
import { Ionicons } from "@expo/vector-icons";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "expo-router";
import React, { useState } from "react";
import { useForm } from "react-hook-form";
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Button } from "@/src/components/Button";
import { ProfileFormFields } from "@/src/components/ProfileFormFields";
import { profileSchema, type ProfileFormValues } from "@/src/schemas/profile";
import { useAuthStore } from "@/src/store/useAuthStore";
import { colors, spacing, typography } from "@/src/theme";

export default function CompleteProfileScreen() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const updateProfile = useAuthStore((s) => s.updateProfile);
  const logout = useAuthStore((s) => s.logout);

  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    control,
    handleSubmit,
    formState: { errors, isSubmitting, isValid },
  } = useForm<ProfileFormValues>({
    resolver: zodResolver(profileSchema),
    mode: "onSubmit",
    reValidateMode: "onSubmit",
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

  const onSubmit = async (values: ProfileFormValues) => {
    setSubmitError(null);
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
      router.replace("/(tabs)");
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : "Failed to save profile");
    }
  };

  return (
    <SafeAreaView style={styles.container} edges={["top", "bottom"]} testID="complete-profile-screen">
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          <Text style={styles.eyebrow}>WELCOME TO DIU TURF</Text>
          <Text style={styles.title}>Complete profile</Text>
          <Text style={styles.subtitle}>
            Add your details so teammates can see who booked each slot.
          </Text>

          {user?.email ? (
            <ProfileFormFields control={control} errors={errors} email={user.email} />
          ) : null}

          {submitError ? (
            <View style={styles.errorBox} testID="profile-submit-error">
              <Ionicons name="alert-circle" size={16} color={colors.danger} />
              <Text style={styles.errorText}>{submitError}</Text>
            </View>
          ) : null}

          <View style={{ marginTop: spacing.xl, gap: spacing.md }}>
            <Button
              label="Continue"
              onPress={handleSubmit(onSubmit)}
              loading={isSubmitting}
              disabled={!isValid}
              testID="profile-submit-button"
            />
            <Button label="Sign out" variant="ghost" onPress={logout} testID="profile-signout-button" />
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  scroll: { flexGrow: 1, padding: spacing.lg },
  eyebrow: { ...typography.label, color: colors.text_secondary, marginBottom: spacing.sm },
  title: { ...typography.h1, color: colors.text_primary },
  subtitle: { ...typography.body, color: colors.text_secondary, marginTop: spacing.md, marginBottom: spacing.lg },
  errorBox: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    backgroundColor: colors.danger_bg,
    borderRadius: 12,
    padding: spacing.md,
    marginTop: spacing.md,
  },
  errorText: { ...typography.body, color: colors.danger, flex: 1 },
});
