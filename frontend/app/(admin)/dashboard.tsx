/** Admin Control Room — Phase 4.
 * KPIs, students count, maintenance + announcement quick actions, audit feed.
 */
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import React, { useCallback, useEffect, useState } from "react";
import {
  Modal,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";

import { Button } from "@/src/components/Button";
import { Card } from "@/src/components/Card";
import { ErrorState } from "@/src/components/ErrorState";
import { ScreenHeader } from "@/src/components/ScreenHeader";
import { SkeletonCard } from "@/src/components/Skeleton";
import { Toast, type ToastMessage } from "@/src/components/Toast";
import { api } from "@/src/services/api";
import { useAuthStore } from "@/src/store/useAuthStore";
import { colors, radii, spacing, typography } from "@/src/theme";
import { getFriendlyErrorMessage } from "@/src/utils/errors";

interface Kpis {
  bookings_today: number;
  utilization_today_pct: number;
  available_slots_today: number;
  active_students: number;
  maintenance_days: number;
  waitlist_pending: number;
  upcoming_reservations: number;
  attendance_rate_pct: number;
  cancellation_rate_pct: number;
}

interface AuditRow {
  audit_id: string;
  action: string;
  admin_email: string;
  description: string;
  timestamp: string;
  target_id: string;
}

export default function AdminDashboard() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [kpis, setKpis] = useState<Kpis | null>(null);
  const [audit, setAudit] = useState<AuditRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Modals
  const [maintModal, setMaintModal] = useState(false);
  const [annModal, setAnnModal] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [maintDate, setMaintDate] = useState("");
  const [maintReason, setMaintReason] = useState("");
  const [annTitle, setAnnTitle] = useState("");
  const [annMsg, setAnnMsg] = useState("");

  const load = useCallback(async () => {
    try {
      const [k, a] = await Promise.all([
        api.get<Kpis>("/api/admin/kpis"),
        api.get<AuditRow[]>("/api/admin/audit?limit=20"),
      ]);
      setKpis(k);
      setAudit(a);
      setLoadError(null);
    } catch (e) {
      setLoadError(getFriendlyErrorMessage(e, "Unable to load. Try again."));
      setToast({ kind: "error", text: getFriendlyErrorMessage(e) });
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const scheduleMaintenance = async () => {
    setSubmitting(true);
    try {
      await api.post("/api/admin/maintenance", { date: maintDate.trim(), reason: maintReason.trim() });
      setMaintModal(false); setMaintDate(""); setMaintReason("");
      setToast({ kind: "success", text: "Maintenance scheduled" });
      await load();
    } catch (e) {
      setToast({ kind: "error", text: e instanceof Error ? e.message : "Failed" });
    } finally {
      setSubmitting(false);
    }
  };

  const sendAnnouncement = async () => {
    setSubmitting(true);
    try {
      await api.post("/api/admin/announcements", { title: annTitle.trim(), message: annMsg.trim() });
      setAnnModal(false); setAnnTitle(""); setAnnMsg("");
      setToast({ kind: "success", text: "Announcement broadcast" });
      await load();
    } catch (e) {
      setToast({ kind: "error", text: e instanceof Error ? e.message : "Failed" });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={styles.container} edges={["top"]} testID="admin-dashboard-screen">
      <Toast message={toast} onHide={() => setToast(null)} />
      <ScreenHeader eyebrow="ADMIN · CONTROL ROOM" title={`Welcome, ${user?.name?.split(" ")[0] ?? "Admin"}`} subtitle={user?.email} />

      <ScrollView
        contentContainerStyle={[styles.scroll, { paddingBottom: insets.bottom + spacing.xxl }]}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={colors.primary} />}
      >
        {loading || !kpis ? (
          loadError ? (
            <ErrorState message={loadError} onRetry={() => { setLoading(true); load(); }} testID="admin-dashboard-error" />
          ) : (
            <View style={{ gap: spacing.sm }}>
              <SkeletonCard />
              <SkeletonCard lines={2} />
            </View>
          )
        ) : (
          <>
            <Text style={styles.section}>OPERATIONAL KPIS</Text>
            <View style={styles.kpiGrid}>
              <Kpi testID="kpi-bookings-today" label="Bookings today" value={kpis.bookings_today} />
              <Kpi testID="kpi-utilization" label="Utilization" value={`${kpis.utilization_today_pct}%`} />
              <Kpi testID="kpi-available" label="Available now" value={kpis.available_slots_today} />
              <Kpi testID="kpi-students" label="Active students" value={kpis.active_students} />
              <Kpi testID="kpi-maintenance" label="Maintenance days" value={kpis.maintenance_days} />
              <Kpi testID="kpi-waitlist" label="Waitlist pending" value={kpis.waitlist_pending} />
              <Kpi testID="kpi-upcoming" label="Upcoming bookings" value={kpis.upcoming_reservations} />
              <Kpi testID="kpi-attendance" label="Attendance rate" value={`${kpis.attendance_rate_pct}%`} />
              <Kpi testID="kpi-cancellation" label="Cancellation rate" value={`${kpis.cancellation_rate_pct}%`} />
            </View>

            <Text style={styles.section}>QUICK ACTIONS</Text>
            <View style={{ gap: spacing.sm }}>
              <Button label="Manage students" variant="secondary" onPress={() => router.push("/(admin)/(tabs)/students")} testID="admin-action-students" />
              <Button label="Manage slots" variant="secondary" onPress={() => router.push("/(admin)/slots")} testID="admin-action-slots" />
              <Button label="Schedule maintenance" variant="secondary" onPress={() => setMaintModal(true)} testID="admin-action-maintenance" />
              <Button label="Send announcement" variant="secondary" onPress={() => setAnnModal(true)} testID="admin-action-announcement" />
            </View>

            <Text style={styles.section}>AUDIT LOG</Text>
            {audit.length === 0 ? (
              <Card testID="audit-empty">
                <Text style={styles.muted}>No admin actions yet.</Text>
              </Card>
            ) : (
              audit.map((row) => (
                <View key={row.audit_id} style={styles.auditRow} testID={`audit-${row.audit_id}`}>
                  <Ionicons name="shield-checkmark-outline" size={18} color={colors.text_secondary} />
                  <View style={{ flex: 1 }}>
                    <Text style={styles.auditAction}>{row.action.replace(/_/g, " ")}</Text>
                    <Text style={styles.auditDesc} numberOfLines={2}>{row.description}</Text>
                    <Text style={styles.auditMeta}>
                      {new Date(row.timestamp).toLocaleString()} · {row.admin_email}
                    </Text>
                  </View>
                </View>
              ))
            )}
          </>
        )}

        <View style={{ marginTop: spacing.xl }}>
          <Button label="Sign out" variant="secondary" onPress={logout} testID="admin-signout-button" />
        </View>
      </ScrollView>

      {/* Maintenance modal */}
      <Modal visible={maintModal} transparent animationType="fade" onRequestClose={() => !submitting && setMaintModal(false)}>
        <View style={styles.modalBackdrop} testID="maintenance-modal">
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>Schedule maintenance</Text>
            <Text style={styles.modalLabel}>Date (YYYY-MM-DD)</Text>
            <TextInput
              value={maintDate}
              onChangeText={setMaintDate}
              placeholder="2026-06-15"
              placeholderTextColor={colors.text_tertiary}
              autoCapitalize="none"
              style={styles.input}
              testID="maintenance-date-input"
            />
            <Text style={styles.modalLabel}>Reason</Text>
            <TextInput
              value={maintReason}
              onChangeText={setMaintReason}
              placeholder="e.g. Field re-turfing"
              placeholderTextColor={colors.text_tertiary}
              style={[styles.input, { minHeight: 80 }]}
              multiline
              testID="maintenance-reason-input"
            />
            <View style={{ height: spacing.lg }} />
            <Button label="Schedule" onPress={scheduleMaintenance} loading={submitting} testID="maintenance-submit" />
            <View style={{ height: spacing.sm }} />
            <Button label="Cancel" variant="ghost" onPress={() => setMaintModal(false)} disabled={submitting} testID="maintenance-cancel" />
          </View>
        </View>
      </Modal>

      {/* Announcement modal */}
      <Modal visible={annModal} transparent animationType="fade" onRequestClose={() => !submitting && setAnnModal(false)}>
        <View style={styles.modalBackdrop} testID="announcement-modal">
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>Send announcement</Text>
            <Text style={styles.modalLabel}>Title</Text>
            <TextInput
              value={annTitle}
              onChangeText={setAnnTitle}
              placeholder="Tournament registration open"
              placeholderTextColor={colors.text_tertiary}
              style={styles.input}
              testID="announcement-title-input"
            />
            <Text style={styles.modalLabel}>Message</Text>
            <TextInput
              value={annMsg}
              onChangeText={setAnnMsg}
              placeholder="Body of the announcement"
              placeholderTextColor={colors.text_tertiary}
              style={[styles.input, { minHeight: 120 }]}
              multiline
              testID="announcement-message-input"
            />
            <View style={{ height: spacing.lg }} />
            <Button label="Broadcast" onPress={sendAnnouncement} loading={submitting} testID="announcement-submit" />
            <View style={{ height: spacing.sm }} />
            <Button label="Cancel" variant="ghost" onPress={() => setAnnModal(false)} disabled={submitting} testID="announcement-cancel" />
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const Kpi: React.FC<{ label: string; value: string | number; testID: string }> = ({ label, value, testID }) => (
  <View style={styles.kpi} testID={testID}>
    <Text style={styles.kpiValue}>{value}</Text>
    <Text style={styles.kpiLabel}>{label}</Text>
  </View>
);

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  scroll: { paddingHorizontal: spacing.lg, paddingTop: spacing.sm, gap: spacing.sm },
  section: { ...typography.label, color: colors.text_secondary, marginTop: spacing.lg, marginBottom: spacing.sm },
  kpiGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  kpi: {
    width: "31%",
    flexGrow: 1, minWidth: 110,
    backgroundColor: colors.surface, borderRadius: radii.md,
    borderWidth: 1, borderColor: colors.border,
    paddingVertical: spacing.md, paddingHorizontal: spacing.sm,
  },
  kpiValue: { ...typography.h2, color: colors.text_primary, fontSize: 26 },
  kpiLabel: { ...typography.caption, marginTop: 2, fontSize: 11 },
  muted: { ...typography.caption, color: colors.text_secondary, textAlign: "center" },
  auditRow: {
    flexDirection: "row", alignItems: "flex-start", gap: spacing.sm,
    paddingVertical: spacing.md, paddingHorizontal: spacing.md,
    backgroundColor: colors.surface, borderRadius: radii.md,
    borderWidth: 1, borderColor: colors.border, marginTop: spacing.sm,
  },
  auditAction: { ...typography.bodyBold, color: colors.text_primary, fontSize: 13 },
  auditDesc: { ...typography.body, color: colors.text_secondary, marginTop: 2 },
  auditMeta: { ...typography.caption, marginTop: 2 },
  modalBackdrop: { flex: 1, backgroundColor: "rgba(15,23,42,0.55)", justifyContent: "center", padding: spacing.lg },
  modalCard: { backgroundColor: colors.background, borderRadius: radii.lg, padding: spacing.lg },
  modalTitle: { ...typography.h2, color: colors.text_primary, marginBottom: spacing.md },
  modalLabel: { ...typography.label, color: colors.text_secondary, marginTop: spacing.sm, marginBottom: spacing.xs },
  input: {
    minHeight: 48, backgroundColor: colors.surface_secondary, borderRadius: radii.md,
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    fontSize: 16, color: colors.text_primary,
  },
});
