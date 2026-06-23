/** Request booking access — profile data is read-only from the signed-in account. */
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import React, { useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Button } from "@/src/components/Button";
import { Card } from "@/src/components/Card";
import { ScreenHeader } from "@/src/components/ScreenHeader";
import { Toast, type ToastMessage } from "@/src/components/Toast";
import { useAccessRequest } from "@/src/hooks/useAccessRequest";
import { useAuthStore } from "@/src/store/useAuthStore";
import { colors, radii, spacing, typography } from "@/src/theme";
import { canBookSlots, roleDisplayLabel } from "@/src/utils/roles";
import { getFriendlyErrorMessage } from "@/src/utils/errors";

function statusLabel(status: string): string {
  if (status === "pending") return "Pending approval";
  if (status === "approved") return "Approved";
  if (status === "rejected") return "Not approved";
  return status;
}

export default function RequestAccessScreen() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const { request, loading, submitting, submit, reload } = useAccessRequest();
  const [reason, setReason] = useState("");
  const [toast, setToast] = useState<ToastMessage | null>(null);

  const hasBookingAccess = canBookSlots(user?.role);
  const canSubmit = !hasBookingAccess && request?.status !== "pending" && request?.status !== "approved";

  const handleSubmit = async () => {
    try {
      await submit(reason);
      setReason("");
      setToast({ kind: "success", text: "Request submitted — pending approval" });
    } catch (e) {
      setToast({ kind: "error", text: getFriendlyErrorMessage(e, "Could not submit request") });
    }
  };

  return (
    <SafeAreaView style={styles.container} edges={["top"]} testID="request-access-screen">
      <Toast message={toast} onHide={() => setToast(null)} />
      <View style={styles.topBar}>
        <Pressable onPress={() => router.back()} hitSlop={8} testID="request-access-back">
          <Ionicons name="chevron-back" size={26} color={colors.text_primary} />
        </Pressable>
      </View>
      <ScreenHeader
        eyebrow="BOOKING ACCESS"
        title="Request Booking Access"
        subtitle="Your profile details are sent automatically."
      />

      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        <Card testID="request-access-profile-card">
          <Text style={styles.sectionTitle}>Your registered profile</Text>
          <InfoRow label="Name" value={user?.name ?? "—"} />
          <InfoRow label="Email" value={user?.email ?? "—"} />
          <InfoRow label="Student ID" value={user?.student_id ?? "—"} />
          <InfoRow label="Current access" value={roleDisplayLabel(user?.role)} />
        </Card>

        {loading ? (
          <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.lg }} />
        ) : null}

        {hasBookingAccess ? (
          <View style={styles.statusBox} testID="request-access-approved">
            <Ionicons name="checkmark-circle" size={22} color={colors.status_available} />
            <Text style={styles.statusText}>You already have booking access.</Text>
          </View>
        ) : null}

        {!hasBookingAccess && request ? (
          <View style={styles.statusBox} testID="request-access-status">
            <Ionicons
              name={request.status === "rejected" ? "close-circle" : "time-outline"}
              size={22}
              color={request.status === "rejected" ? colors.danger : colors.primary}
            />
            <Text style={styles.statusText}>{statusLabel(request.status)}</Text>
            {request.status === "pending" ? (
              <Text style={styles.statusHint}>An admin will review your request soon.</Text>
            ) : null}
            {request.status === "rejected" ? (
              <Text style={styles.statusHint}>You can submit a new request below.</Text>
            ) : null}
          </View>
        ) : null}

        {canSubmit ? (
          <View style={styles.form}>
            <Text style={styles.label}>Reason (optional)</Text>
            <TextInput
              style={styles.input}
              value={reason}
              onChangeText={setReason}
              placeholder="Why do you need booking access?"
              placeholderTextColor={colors.text_tertiary}
              multiline
              maxLength={500}
              testID="request-access-reason"
            />
            <Button
              label="Submit request"
              onPress={handleSubmit}
              loading={submitting}
              disabled={submitting}
              leftIcon={<Ionicons name="star-outline" size={18} color="#FFFFFF" />}
              testID="request-access-submit"
            />
          </View>
        ) : null}

        {!hasBookingAccess ? (
          <Pressable onPress={() => reload()} style={styles.refreshLink} testID="request-access-refresh">
            <Text style={styles.refreshText}>Refresh status</Text>
          </Pressable>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.infoRow}>
      <Text style={styles.infoLabel}>{label}</Text>
      <Text style={styles.infoValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  topBar: { paddingHorizontal: spacing.lg, paddingTop: spacing.sm },
  scroll: { padding: spacing.lg, paddingBottom: spacing.xxl, gap: spacing.md },
  sectionTitle: { ...typography.label, color: colors.text_secondary, marginBottom: spacing.sm },
  infoRow: { marginBottom: spacing.sm },
  infoLabel: { ...typography.caption, color: colors.text_tertiary },
  infoValue: { ...typography.body, color: colors.text_primary },
  statusBox: {
    padding: spacing.md,
    borderRadius: radii.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    gap: spacing.xs,
  },
  statusText: { ...typography.bodyBold, color: colors.text_primary },
  statusHint: { ...typography.caption, color: colors.text_secondary },
  form: { gap: spacing.sm },
  label: { ...typography.caption, color: colors.text_secondary, fontWeight: "600" },
  input: {
    minHeight: 96,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    padding: spacing.md,
    ...typography.body,
    color: colors.text_primary,
    backgroundColor: colors.surface,
    textAlignVertical: "top",
  },
  refreshLink: { alignSelf: "center", paddingVertical: spacing.sm },
  refreshText: { ...typography.caption, color: colors.primary, fontWeight: "600" },
});
