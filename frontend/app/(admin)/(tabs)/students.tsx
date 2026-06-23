/** Admin > Students tab — reuses list without back navigation. */
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";

import { Button } from "@/src/components/Button";
import { EmptyState } from "@/src/components/EmptyState";
import { ScreenHeader } from "@/src/components/ScreenHeader";
import { SkeletonList } from "@/src/components/Skeleton";
import { Toast, type ToastMessage } from "@/src/components/Toast";
import {
  adminService,
  type StudentListItem,
  type StudentStats,
  type StudentStatus,
} from "@/src/services/adminService";
import { colors, radii, spacing, typography } from "@/src/theme";
import { getFriendlyErrorMessage } from "@/src/utils/errors";

const PAGE_SIZE = 20;

function statusLabel(status: StudentStatus): string {
  if (status === "suspended") return "Suspended";
  if (status === "inactive") return "Inactive";
  return "Active";
}

function statusColors(status: StudentStatus): { bg: string; fg: string } {
  if (status === "suspended") return { bg: colors.status_maintenance_bg, fg: colors.status_maintenance };
  if (status === "inactive") return { bg: colors.status_booked_bg, fg: colors.status_booked };
  return { bg: colors.status_available_bg, fg: colors.status_available };
}

function formatCreatedAt(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString();
}

export default function AdminStudentsTabScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [query, setQuery] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<StudentListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<StudentStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [toast, setToast] = useState<ToastMessage | null>(null);

  useEffect(() => {
    const id = setTimeout(() => {
      setDebouncedQ(query.trim());
      setPage(1);
    }, 350);
    return () => clearTimeout(id);
  }, [query]);

  const totalPages = useMemo(() => Math.max(1, Math.ceil(total / PAGE_SIZE)), [total]);

  const load = useCallback(async () => {
    try {
      const data = await adminService.listStudents({
        q: debouncedQ || undefined,
        page,
        page_size: PAGE_SIZE,
      });
      setItems(data.items);
      setTotal(data.total);
      setStats(data.stats);
    } catch (e) {
      setToast({ kind: "error", text: getFriendlyErrorMessage(e) });
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [debouncedQ, page]);

  useEffect(() => {
    setLoading(true);
    load();
  }, [load]);

  const renderRow = ({ item }: { item: StudentListItem }) => {
    const badge = statusColors(item.status);
    return (
      <TouchableOpacity
        style={styles.row}
        onPress={() => router.push(`/(admin)/student/${item.user_id}`)}
        testID={`student-row-${item.user_id}`}
      >
        <View style={styles.rowMain}>
          <Text style={styles.rowName} numberOfLines={1}>{item.name}</Text>
          <Text style={styles.rowMeta} numberOfLines={1}>
            {item.student_id ?? "—"} · {item.email}
          </Text>
          <Text style={styles.rowMeta} numberOfLines={1}>
            Batch {item.batch ?? "—"} · Room {item.room_number ?? "—"}
          </Text>
          <Text style={styles.rowBookings} numberOfLines={1}>
            Joined {formatCreatedAt(item.created_at)}
            {" · "}
            {item.booking_count ?? 0} booking{(item.booking_count ?? 0) === 1 ? "" : "s"}
          </Text>
        </View>
        <View style={[styles.badge, { backgroundColor: badge.bg }]}>
          <Text style={[styles.badgeText, { color: badge.fg }]}>{statusLabel(item.status)}</Text>
        </View>
        <Ionicons name="chevron-forward" size={18} color={colors.text_tertiary} />
      </TouchableOpacity>
    );
  };

  return (
    <SafeAreaView style={styles.container} edges={["top"]} testID="admin-students-screen">
      <Toast message={toast} onHide={() => setToast(null)} />
      <ScreenHeader
        eyebrow="ADMIN · STUDENTS"
        title="Student management"
        subtitle="Search and manage all users"
      />

      <View style={styles.searchWrap}>
        <Ionicons name="search-outline" size={18} color={colors.text_tertiary} />
        <TextInput
          value={query}
          onChangeText={setQuery}
          placeholder="Search by ID, name, or email"
          placeholderTextColor={colors.text_tertiary}
          autoCapitalize="none"
          autoCorrect={false}
          style={styles.searchInput}
          testID="students-search-input"
        />
        {query.length > 0 ? (
          <TouchableOpacity onPress={() => setQuery("")} testID="students-search-clear">
            <Ionicons name="close-circle" size={18} color={colors.text_tertiary} />
          </TouchableOpacity>
        ) : null}
      </View>

      {stats ? (
        <View style={styles.statsRow}>
          <StatBox label="Total users" value={stats.total} testID="stat-total-students" />
          <StatBox label="Active" value={stats.active} testID="stat-active-students" />
          <StatBox label="Suspended" value={stats.suspended} testID="stat-suspended-students" />
        </View>
      ) : null}

      {loading && items.length === 0 ? (
        <View style={{ paddingHorizontal: spacing.lg, marginTop: spacing.md }}>
          <SkeletonList count={6} />
        </View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(item) => item.user_id}
          renderItem={renderRow}
          contentContainerStyle={{ paddingHorizontal: spacing.lg, paddingBottom: insets.bottom + spacing.xxl }}
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
          ListHeaderComponent={
            <View style={styles.tableHead}>
              <Text style={[styles.colHead, { flex: 1 }]}>Student · email · batch · room</Text>
              <Text style={styles.colHead}>Status</Text>
            </View>
          }
          ListEmptyComponent={
            !loading ? (
              <EmptyState
                icon="people-outline"
                title="No users found"
                subtitle="Try a different search term."
                testID="students-empty"
              />
            ) : null
          }
          ListFooterComponent={
            totalPages > 1 ? (
              <View style={styles.pagination}>
                <Button
                  label="Previous"
                  variant="secondary"
                  onPress={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1 || loading}
                  testID="students-prev-page"
                  fullWidth={false}
                  style={styles.pageBtn}
                />
                <Text style={styles.pageLabel} testID="students-page-label">
                  Page {page} of {totalPages}
                </Text>
                <Button
                  label="Next"
                  variant="secondary"
                  onPress={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages || loading}
                  testID="students-next-page"
                  fullWidth={false}
                  style={styles.pageBtn}
                />
              </View>
            ) : null
          }
        />
      )}
    </SafeAreaView>
  );
}

const StatBox: React.FC<{ label: string; value: number; testID: string }> = ({ label, value, testID }) => (
  <View style={styles.statBox} testID={testID}>
    <Text style={styles.statValue}>{value}</Text>
    <Text style={styles.statLabel}>{label}</Text>
  </View>
);

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  searchWrap: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    marginHorizontal: spacing.lg,
    marginBottom: spacing.md,
    backgroundColor: colors.surface_secondary,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    minHeight: 48,
  },
  searchInput: { flex: 1, fontSize: 16, color: colors.text_primary },
  statsRow: { flexDirection: "row", gap: spacing.sm, paddingHorizontal: spacing.lg, marginBottom: spacing.md },
  statBox: {
    flex: 1,
    backgroundColor: colors.surface,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.sm,
    alignItems: "center",
  },
  statValue: { ...typography.h2, fontSize: 24, color: colors.text_primary },
  statLabel: { ...typography.caption, marginTop: 2, fontSize: 11 },
  tableHead: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    marginBottom: spacing.xs,
  },
  colHead: { ...typography.label, color: colors.text_tertiary, fontSize: 10 },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  rowMain: { flex: 1 },
  rowName: { ...typography.bodyBold, color: colors.text_primary },
  rowMeta: { ...typography.caption, marginTop: 2 },
  rowBookings: { ...typography.caption, marginTop: 2, color: colors.text_tertiary, fontSize: 11 },
  bookingCount: { ...typography.label, width: 56, textAlign: "right", color: colors.text_secondary },
  badge: { borderRadius: radii.pill, paddingHorizontal: spacing.sm, paddingVertical: 4 },
  badgeText: { ...typography.label, fontSize: 10 },
  muted: { ...typography.caption, color: colors.text_secondary, textAlign: "center" },
  pagination: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: spacing.lg,
    gap: spacing.sm,
  },
  pageBtn: { minWidth: 100 },
  pageLabel: { ...typography.caption, color: colors.text_secondary },
});
