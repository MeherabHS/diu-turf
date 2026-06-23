/** Shared profile form fields for complete-profile and profile edit screens. */
import React from "react";
import { Control, Controller, FieldErrors } from "react-hook-form";
import { StyleSheet, Text, TextInput, View } from "react-native";

import type { ProfileFormValues } from "@/src/schemas/profile";
import { colors, radii, spacing, typography } from "@/src/theme";

interface FieldProps {
  label: string;
  required?: boolean;
  error?: string;
  hint?: string;
  testID: string;
  children: React.ReactNode;
}

const Field: React.FC<FieldProps> = ({ label, required, error, hint, testID, children }) => (
  <View style={styles.field} testID={testID}>
    <Text style={styles.label}>
      {label}
      {required ? <Text style={styles.required}> *</Text> : null}
    </Text>
    {children}
    {error ? <Text style={styles.fieldError}>{error}</Text> : hint ? <Text style={styles.hint}>{hint}</Text> : null}
  </View>
);

interface ProfileFormFieldsProps {
  control: Control<ProfileFormValues>;
  errors: FieldErrors<ProfileFormValues>;
  email: string;
}

export function ProfileFormFields({ control, errors, email }: ProfileFormFieldsProps) {
  return (
    <>
      <Field label="Email" required testID="profile-field-email">
        <View style={[styles.input, styles.inputDisabled]}>
          <Text style={styles.inputDisabledText} testID="profile-email-readonly">{email}</Text>
        </View>
      </Field>

      <Controller
        control={control}
        name="name"
        render={({ field: { value, onChange, onBlur } }) => (
          <Field label="Full Name" required testID="profile-field-name" error={errors.name?.message}>
            <TextInput
              value={value}
              onChangeText={onChange}
              onBlur={onBlur}
              placeholder="e.g. Meherab Hossain Shafin"
              placeholderTextColor={colors.text_tertiary}
              autoCapitalize="words"
              autoCorrect={false}
              style={styles.input}
              maxLength={80}
              testID="profile-name-input"
            />
          </Field>
        )}
      />

      <Controller
        control={control}
        name="student_id"
        render={({ field: { value, onChange, onBlur } }) => (
          <Field label="Student ID" required testID="profile-field-student-id" error={errors.student_id?.message}>
            <TextInput
              value={value}
              onChangeText={onChange}
              onBlur={onBlur}
              placeholder="e.g. 252-35-166"
              placeholderTextColor={colors.text_tertiary}
              autoCapitalize="characters"
              autoCorrect={false}
              style={styles.input}
              maxLength={32}
              testID="profile-student-id-input"
            />
          </Field>
        )}
      />

      <Controller
        control={control}
        name="department"
        render={({ field: { value, onChange, onBlur } }) => (
          <Field label="Department" required testID="profile-field-department" error={errors.department?.message}>
            <TextInput
              value={value ?? ""}
              onChangeText={onChange}
              onBlur={onBlur}
              placeholder="e.g. SWE"
              placeholderTextColor={colors.text_tertiary}
              autoCapitalize="characters"
              autoCorrect={false}
              style={styles.input}
              maxLength={100}
              testID="profile-department-input"
            />
          </Field>
        )}
      />

      <Controller
        control={control}
        name="batch"
        render={({ field: { value, onChange, onBlur } }) => (
          <Field label="Batch" required testID="profile-field-batch" error={errors.batch?.message}>
            <TextInput
              value={value ?? ""}
              onChangeText={onChange}
              onBlur={onBlur}
              placeholder="e.g. 47"
              placeholderTextColor={colors.text_tertiary}
              autoCorrect={false}
              style={styles.input}
              maxLength={50}
              testID="profile-batch-input"
            />
          </Field>
        )}
      />

      <Controller
        control={control}
        name="room_number"
        render={({ field: { value, onChange, onBlur } }) => (
          <Field label="Room Number" testID="profile-field-room" error={errors.room_number?.message} hint="Recommended">
            <TextInput
              value={value ?? ""}
              onChangeText={onChange}
              onBlur={onBlur}
              placeholder="e.g. 402"
              placeholderTextColor={colors.text_tertiary}
              autoCorrect={false}
              style={styles.input}
              maxLength={20}
              testID="profile-room-input"
            />
          </Field>
        )}
      />

      <Controller
        control={control}
        name="hostel_name"
        render={({ field: { value, onChange, onBlur } }) => (
          <Field label="Hostel / Hall Name" testID="profile-field-hostel" error={errors.hostel_name?.message}>
            <TextInput
              value={value ?? ""}
              onChangeText={onChange}
              onBlur={onBlur}
              placeholder="e.g. DIU Boys Hostel"
              placeholderTextColor={colors.text_tertiary}
              autoCapitalize="words"
              autoCorrect={false}
              style={styles.input}
              maxLength={100}
              testID="profile-hostel-input"
            />
          </Field>
        )}
      />

      <Controller
        control={control}
        name="phone"
        render={({ field: { value, onChange, onBlur } }) => (
          <Field label="Phone Number" testID="profile-field-phone" error={errors.phone?.message} hint="Optional">
            <TextInput
              value={value ?? ""}
              onChangeText={onChange}
              onBlur={onBlur}
              placeholder="e.g. 01XXXXXXXXX"
              placeholderTextColor={colors.text_tertiary}
              keyboardType="phone-pad"
              autoCorrect={false}
              style={styles.input}
              maxLength={20}
              testID="profile-phone-input"
            />
          </Field>
        )}
      />
    </>
  );
}

const styles = StyleSheet.create({
  field: { marginTop: spacing.md },
  label: { ...typography.label, marginBottom: spacing.sm, color: colors.text_secondary },
  required: { color: colors.danger },
  input: {
    minHeight: 56,
    backgroundColor: colors.surface_secondary,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontSize: 16,
    fontWeight: "500",
    color: colors.text_primary,
    justifyContent: "center",
  },
  inputDisabled: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  inputDisabledText: { color: colors.text_secondary, fontSize: 16 },
  fieldError: { ...typography.caption, color: colors.danger, marginTop: spacing.xs },
  hint: { ...typography.caption, marginTop: spacing.xs },
});
