/** Register screen — DIU email + password with strict student ID matching. */
import { Ionicons } from "@expo/vector-icons";
import { zodResolver } from "@hookform/resolvers/zod";
import { Link } from "expo-router";
import React, { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Button } from "@/src/components/Button";
import { ALLOWED_EMAIL_DOMAIN } from "@/src/constants";
import { registerSchema, type RegisterFormValues } from "@/src/schemas/register";
import { useAuthStore } from "@/src/store/useAuthStore";
import { colors, radii, spacing, typography } from "@/src/theme";

function Field({
  label,
  required,
  error,
  testID,
  children,
}: {
  label: string;
  required?: boolean;
  error?: string;
  testID: string;
  children: React.ReactNode;
}) {
  return (
    <View style={styles.field} testID={testID}>
      <Text style={styles.label}>
        {label}
        {required ? <Text style={styles.required}> *</Text> : null}
      </Text>
      {children}
      {error ? <Text style={styles.fieldError}>{error}</Text> : null}
    </View>
  );
}

export default function RegisterScreen() {
  const registerWithPassword = useAuthStore((s) => s.registerWithPassword);
  const isLoading = useAuthStore((s) => s.isLoading);
  const error = useAuthStore((s) => s.error);
  const setError = useAuthStore((s) => s.setError);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema),
    mode: "onChange",
    defaultValues: {
      full_name: "",
      email: "",
      student_id: "",
      department: "",
      batch: "",
      room_number: "",
      hostel_name: "",
      phone: "",
      password: "",
      confirm_password: "",
    },
  });

  const onSubmit = async (values: RegisterFormValues) => {
    setSubmitError(null);
    setError(null);
    try {
      await registerWithPassword({
        email: values.email.trim().toLowerCase(),
        password: values.password,
        full_name: values.full_name.trim(),
        student_id: values.student_id.trim(),
        department: values.department.trim(),
        batch: values.batch.trim(),
        room_number: values.room_number?.trim() || null,
        hostel_name: values.hostel_name?.trim() || null,
        phone: values.phone?.trim() || null,
      });
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : "Registration failed");
    }
  };

  const displayError = submitError || error;

  return (
    <SafeAreaView style={styles.container} edges={["top", "bottom"]} testID="register-screen">
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          <Text style={styles.title}>Create account</Text>
          <Text style={styles.helper}>
            Use your own DIU student email. Your student ID must match your email.
          </Text>

          {displayError ? (
            <View style={styles.errorBox} testID="register-error">
              <Ionicons name="alert-circle" size={18} color={colors.danger} />
              <Text style={styles.errorText}>{displayError}</Text>
            </View>
          ) : null}

          <Controller
            control={control}
            name="full_name"
            render={({ field: { value, onChange, onBlur } }) => (
              <Field label="Full name" required testID="register-field-name" error={errors.full_name?.message}>
                <TextInput
                  style={styles.input}
                  value={value}
                  onChangeText={onChange}
                  onBlur={onBlur}
                  placeholder="Your full name"
                  placeholderTextColor={colors.text_tertiary}
                  autoCapitalize="words"
                  testID="register-name-input"
                />
              </Field>
            )}
          />

          <Controller
            control={control}
            name="email"
            render={({ field: { value, onChange, onBlur } }) => (
              <Field label="DIU email" required testID="register-field-email" error={errors.email?.message}>
                <TextInput
                  style={styles.input}
                  value={value}
                  onChangeText={onChange}
                  onBlur={onBlur}
                  placeholder={`252-35-166${ALLOWED_EMAIL_DOMAIN}`}
                  placeholderTextColor={colors.text_tertiary}
                  autoCapitalize="none"
                  keyboardType="email-address"
                  testID="register-email-input"
                />
              </Field>
            )}
          />

          <Controller
            control={control}
            name="student_id"
            render={({ field: { value, onChange, onBlur } }) => (
              <Field label="Student ID" required testID="register-field-student-id" error={errors.student_id?.message}>
                <TextInput
                  style={styles.input}
                  value={value}
                  onChangeText={onChange}
                  onBlur={onBlur}
                  placeholder="252-35-166"
                  placeholderTextColor={colors.text_tertiary}
                  autoCapitalize="none"
                  testID="register-student-id-input"
                />
              </Field>
            )}
          />

          <Controller
            control={control}
            name="department"
            render={({ field: { value, onChange, onBlur } }) => (
              <Field label="Department" required testID="register-field-department" error={errors.department?.message}>
                <TextInput
                  style={styles.input}
                  value={value}
                  onChangeText={onChange}
                  onBlur={onBlur}
                  placeholder="e.g. SWE"
                  placeholderTextColor={colors.text_tertiary}
                  testID="register-department-input"
                />
              </Field>
            )}
          />

          <Controller
            control={control}
            name="batch"
            render={({ field: { value, onChange, onBlur } }) => (
              <Field label="Batch" required testID="register-field-batch" error={errors.batch?.message}>
                <TextInput
                  style={styles.input}
                  value={value}
                  onChangeText={onChange}
                  onBlur={onBlur}
                  placeholder="e.g. 47"
                  placeholderTextColor={colors.text_tertiary}
                  testID="register-batch-input"
                />
              </Field>
            )}
          />

          <Controller
            control={control}
            name="room_number"
            render={({ field: { value, onChange, onBlur } }) => (
              <Field label="Room number" testID="register-field-room" error={errors.room_number?.message}>
                <TextInput
                  style={styles.input}
                  value={value}
                  onChangeText={onChange}
                  onBlur={onBlur}
                  placeholder="e.g. 402"
                  placeholderTextColor={colors.text_tertiary}
                  testID="register-room-input"
                />
              </Field>
            )}
          />

          <Controller
            control={control}
            name="hostel_name"
            render={({ field: { value, onChange, onBlur } }) => (
              <Field label="Hostel name" testID="register-field-hostel" error={errors.hostel_name?.message}>
                <TextInput
                  style={styles.input}
                  value={value}
                  onChangeText={onChange}
                  onBlur={onBlur}
                  placeholder="Optional"
                  placeholderTextColor={colors.text_tertiary}
                  testID="register-hostel-input"
                />
              </Field>
            )}
          />

          <Controller
            control={control}
            name="phone"
            render={({ field: { value, onChange, onBlur } }) => (
              <Field label="Phone" testID="register-field-phone" error={errors.phone?.message}>
                <TextInput
                  style={styles.input}
                  value={value}
                  onChangeText={onChange}
                  onBlur={onBlur}
                  placeholder="Optional"
                  placeholderTextColor={colors.text_tertiary}
                  keyboardType="phone-pad"
                  testID="register-phone-input"
                />
              </Field>
            )}
          />

          <Controller
            control={control}
            name="password"
            render={({ field: { value, onChange, onBlur } }) => (
              <Field label="Password" required testID="register-field-password" error={errors.password?.message}>
                <TextInput
                  style={styles.input}
                  value={value}
                  onChangeText={onChange}
                  onBlur={onBlur}
                  placeholder="At least 8 characters"
                  placeholderTextColor={colors.text_tertiary}
                  secureTextEntry
                  autoCapitalize="none"
                  testID="register-password-input"
                />
              </Field>
            )}
          />

          <Controller
            control={control}
            name="confirm_password"
            render={({ field: { value, onChange, onBlur } }) => (
              <Field
                label="Confirm password"
                required
                testID="register-field-confirm-password"
                error={errors.confirm_password?.message}
              >
                <TextInput
                  style={styles.input}
                  value={value}
                  onChangeText={onChange}
                  onBlur={onBlur}
                  placeholder="Re-enter password"
                  placeholderTextColor={colors.text_tertiary}
                  secureTextEntry
                  autoCapitalize="none"
                  testID="register-confirm-password-input"
                />
              </Field>
            )}
          />

          <Button
            label="Create account"
            onPress={handleSubmit(onSubmit)}
            loading={isLoading || isSubmitting}
            testID="register-submit-button"
          />

          <Link href="/(auth)/login" asChild>
            <Text style={styles.link} testID="register-sign-in-link">
              Already have an account? Sign in
            </Text>
          </Link>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  scroll: { padding: spacing.lg, paddingBottom: spacing.xxl, gap: spacing.xs },
  title: { ...typography.h2, color: colors.text_primary, marginBottom: spacing.xs },
  helper: { ...typography.body, color: colors.text_secondary, marginBottom: spacing.md },
  field: { marginBottom: spacing.sm },
  label: { ...typography.caption, color: colors.text_secondary, fontWeight: "600", marginBottom: spacing.xs },
  required: { color: colors.danger },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    ...typography.body,
    color: colors.text_primary,
    backgroundColor: colors.surface,
  },
  fieldError: { ...typography.caption, color: colors.danger, marginTop: spacing.xs },
  errorBox: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: spacing.sm,
    backgroundColor: colors.danger_bg,
    borderRadius: 12,
    padding: spacing.md,
    marginBottom: spacing.sm,
  },
  errorText: { ...typography.body, color: colors.danger, flex: 1 },
  link: {
    ...typography.body,
    color: colors.primary,
    fontWeight: "600",
    textAlign: "center",
    marginTop: spacing.md,
    paddingVertical: spacing.sm,
  },
});
