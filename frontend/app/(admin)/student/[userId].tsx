/** Admin > Student detail — profile, history, suspend/reactivate. */
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import React, { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Modal,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";

import { Button } from "@/src/components/Button";
import { Card } from "@/src/components/Card";
import { ScreenHeader } from "@/src/components/ScreenHeader";
import { Toast, type ToastMessage } from "@/src/components/Toast";
import {
  adminService,
  type StudentDetail,
  type StudentStatus,
  type SuspendDuration,
} from "@/src/services/adminService";
import { colors, radii, spacing, typography } from "@/src/theme";

const DURATIONS: { id: SuspendDuration; label: string }[] = [
  { id: "1d", label: "1 day" },
  { id: "7d", label: "7 days" },
  { id: "30d", label: "30 days" },
  { id: "permanent", label: "Permanent" },
];

function statusLabel(status: StudentStatus): string {
  if (status === "suspended") return "Suspended";
  if (status === "inactive") return "Inactive";
  return "Active";
}

export default function AdminStudentDetailScreen() {
  const { userId } = useLocalSearchParams<{ userId: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [detail, setDetail] = useState<StudentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const [suspendModal, setSuspendModal] = useState(false);
  const [duration, setDuration] = useState<SuspendDuration>("7d");
  const [reason, setReason] = useState("");

  const load = useCallback(async () => {
    if (!userId) return;
    try {
      const data = await adminService.getStudent(userId);
      setDetail(data);
    } catch (e) {
      setToast({ kind: "error", text: e instanceof Error ? e.message : "Failed to load student" });
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [userId]);

  useEffect(() => {
    setLoading(true);
    load();
  }, [load]);

  const suspend = async () => {
    if (!userId || reason.trim().length < 3) {
      setToast({ kind: "error", text: "Reason must be at least 3 characters" });
      return;
    }
    setSubmitting(true);
    try {
      await adminService.suspend(userId, { duration, reason: reason.trim() });
      setSuspendModal(false);
      setReason("");
      setToast({ kind: "success", text: "Student suspended" });
      await load();
    } catch (e) {
      setToast({ kind: "error", text: e instanceof Error ? e.message : "Suspend failed" });
    } finally {
      setSubmitting(false);
    }
  };

  const reactivate = async () => {
    if (!userId) return;
    setSubmitting(true);
    try {
      await adminService.activate(userId);
      setToast({ kind: "success", text: "User activated" });
      await load();
    } catch (e) {
      setToast({ kind: "error", text: e instanceof Error ? e.message : "Activate failed" });
    } finally {
      setSubmitting(false);
    }
  };

  const profile = detail?.profile;

  return (
    <SafeAreaView style={styles.container} edges={["top"]} testID="admin-student-detail-screen">
      <Toast message={toast} onHide={() => setToast(null)} />
      <ScreenHeader
        eyebrow="ADMIN · STUDENT"
        title={profile?.name ?? "Student details"}
        subtitle={profile?.email}
        right={
          <TouchableOpacity onPress={() => router.back()} style={styles.backBtn} testID="student-detail-back">
            <Ionicons name="arrow-back" size={22} color={colors.text_primary} />
          </TouchableOpacity>
        }
      />

      {loading && !detail ? (
        <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xl }} />
      ) : !profile ? (
        <Card style={{ margin: spacing.lg }}>
          <Text style={styles.muted}>Student not found.</Text>
        </Card>
      ) : (
        <ScrollView
          contentContainerStyle={[styles.scroll, { paddingBottom: insets.bottom + spacing.xxl }]}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={() => {
                setRefreshing(true);
                load();
              }}
              tintColor={colors.primary}
            />
          }
        >
          <Text style={styles.section}>PROFILE</Text>
          <Card testID="student-profile-card">
            <ProfileRow label="Student ID" value={profile.student_id ?? "—"} />
            <ProfileRow label="Name" value={profile.name} />
            <ProfileRow label="Email" value={profile.email} />
            <ProfileRow label="Department" value={profile.department ?? "—"} />
            <ProfileRow label="Batch" value={profile.batch ?? "—"} />
            <ProfileRow label="Status" value={statusLabel(profile.status)} />
            {profile.booking_count != null ? (
              <ProfileRow label="Bookings" value={String(profile.booking_count)} />
            ) : null}
            {profile.suspended && profile.suspension_reason ? (
              <ProfileRow label="Suspension reason" value={profile.suspension_reason} />
            ) : null}
            {profile.suspended && profile.suspension_until ? (
              <ProfileRow label="Suspended until" value={new Date(profile.suspension_until).toLocaleString()} />
            ) : null}
            {profile.last_login ? (
              <ProfileRow label="Last login" value={new Date(profile.last_login).toLocaleString()} />
            ) : null}
          </Card>

          <View style={styles.actions}>
            {profile.suspended || profile.status === "inactive" ? (
              <Button
                label="Activate"
                onPress={reactivate}
                loading={submitting}
                testID="student-reactivate-button"
              />
            ) : profile.role === "admin" || profile.role === "super_admin" ? null : (
              <Button
                label="Suspend"
                variant="secondary"
                onPress={() => setSuspendModal(true)}
                disabled={submitting}
                testID="student-suspend-button"
              />
            )}
          </View>

          <HistorySection
            title="BOOKING HISTORY"
            empty="No active bookings."
            testID="student-bookings"
            rows={(detail?.bookings ?? []).map((b) => ({
              id: b.booking_id,
              primary: `${b.booking_date} · ${b.slot_label}`,
              secondary: `${b.time_range} · ${b.status}`,
            }))}
          />

          <HistorySection
            title="ATTENDANCE HISTORY"
            empty="No attendance records."
            testID="student-attendance"
            rows={(detail?.attendance ?? []).map((a, i) => ({
              id: `${a.booking_date}-${a.slot_id}-${i}`,
              primary: `${a.booking_date} · ${a.slot_label}`,
              secondary: `${a.status.toUpperCase()} · ${a.marked_at ? new Date(a.marked_at).toLocaleString() : "—"}`,
            }))}
          />

          <HistorySection
            title="CANCELLATION HISTORY"
            empty="No cancellations."
            testID="student-cancellations"
            rows={(detail?.cancellations ?? []).map((b) => ({
              id: b.booking_id,
              primary: `${b.booking_date} · ${b.slot_label}`,
              secondary: b.cancellation_reason ?? b.cancelled_at ?? "Cancelled",
            }))}
          />
        </ScrollView>
      )}

      <Modal visible={suspendModal} transparent animationType="fade" onRequestClose={() => !submitting && setSuspendModal(false)}>
        <View style={styles.modalBackdrop} testID="suspend-modal">
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>Suspend student</Text>
            <Text style={styles.modalLabel}>Duration</Text>
            <View style={styles.durationRow}>
              {DURATIONS.map((d) => (
                <TouchableOpacity
                  key={d.id}
                  style={[styles.durationChip, duration === d.id && styles.durationChipActive]}
                  onPress={() => setDuration(d.id)}
                  testID={`suspend-duration-${d.id}`}
                >
                  <Text style={[styles.durationText, duration === d.id && styles.durationTextActive]}>{d.label}</Text>
                </TouchableOpacity>
              ))}
            </View>
            <Text style={styles.modalLabel}>Reason</Text>
            <TextInput
              value={reason}
              onChangeText={setReason}
              placeholder="Reason for suspension"
              placeholderTextColor={colors.text_tertiary}
              style={[styles.input, { minHeight: 80 }]}
              multiline
              testID="suspend-reason-input"
            />
            <View style={{ height: spacing.lg }} />
            <Button label="Suspend" onPress={suspend} loading={submitting} testID="suspend-submit" />
            <View style={{ height: spacing.sm }} />
            <Button
              label="Cancel"
              variant="ghost"
              onPress={() => setSuspendModal(false)}
              disabled={submitting}
              testID="suspend-cancel"
            />
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const ProfileRow: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <View style={styles.profileRow}>
    <Text style={styles.profileLabel}>{label}</Text>
    <Text style={styles.profileValue}>{value}</Text>
  </View>
);

const HistorySection: React.FC<{
  title: string;
  empty: string;
  testID: string;
  rows: { id: string; primary: string; secondary: string }[];
}> = ({ title, empty, testID, rows }) => (
  <>
    <Text style={styles.section}>{title}</Text>
    {rows.length === 0 ? (
      <Card testID={`${testID}-empty`}>
        <Text style={styles.muted}>{empty}</Text>
      </Card>
    ) : (
      rows.map((row) => (
        <View key={row.id} style={styles.historyRow} testID={`${testID}-${row.id}`}>
          <Text style={styles.historyPrimary}>{row.primary}</Text>
          <Text style={styles.historySecondary} numberOfLines={2}>{row.secondary}</Text>
        </View>
      ))
    )}
  </>
);

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  backBtn: { padding: spacing.sm, marginTop: spacing.xs },
  scroll: { paddingHorizontal: spacing.lg, paddingTop: spacing.sm },
  section: { ...typography.label, color: colors.text_secondary, marginTop: spacing.lg, marginBottom: spacing.sm },
  profileRow: { marginBottom: spacing.sm },
  profileLabel: { ...typography.caption, color: colors.text_tertiary },
  profileValue: { ...typography.body, color: colors.text_primary, marginTop: 2 },
  actions: { marginTop: spacing.md },
  historyRow: {
    backgroundColor: colors.surface,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    marginBottom: spacing.sm,
  },
  historyPrimary: { ...typography.bodyBold, color: colors.text_primary, fontSize: 14 },
  historySecondary: { ...typography.caption, marginTop: 4 },
  muted: { ...typography.caption, color: colors.text_secondary, textAlign: "center" },
  modalBackdrop: { flex: 1, backgroundColor: "rgba(15,23,42,0.55)", justifyContent: "center", padding: spacing.lg },
  modalCard: { backgroundColor: colors.background, borderRadius: radii.lg, padding: spacing.lg },
  modalTitle: { ...typography.h2, color: colors.text_primary, marginBottom: spacing.md },
  modalLabel: { ...typography.label, color: colors.text_secondary, marginTop: spacing.sm, marginBottom: spacing.xs },
  input: {
    minHeight: 48,
    backgroundColor: colors.surface_secondary,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontSize: 16,
    color: colors.text_primary,
  },
  durationRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  durationChip: {
    borderRadius: radii.pill,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    backgroundColor: colors.surface,
  },
  durationChipActive: { borderColor: colors.primary, backgroundColor: colors.status_available_bg },
  durationText: { ...typography.caption, color: colors.text_secondary },
  durationTextActive: { color: colors.primary_dark, fontWeight: "700" },
});
