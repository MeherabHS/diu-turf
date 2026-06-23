/** Admin — review booking access requests. */
import { Ionicons } from "@expo/vector-icons";
import React, { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Button } from "@/src/components/Button";
import { Card } from "@/src/components/Card";
import { EmptyState } from "@/src/components/EmptyState";
import { ScreenHeader } from "@/src/components/ScreenHeader";
import { Toast, type ToastMessage } from "@/src/components/Toast";
import { adminService, type AccessRequestRow } from "@/src/services/adminService";
import { colors, radii, spacing, typography } from "@/src/theme";
import { getFriendlyErrorMessage } from "@/src/utils/errors";

type Filter = "pending" | "approved" | "rejected" | "all";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "pending", label: "Pending" },
  { key: "approved", label: "Approved" },
  { key: "rejected", label: "Rejected" },
  { key: "all", label: "All" },
];

export default function AdminAccessRequestsScreen() {
  const [filter, setFilter] = useState<Filter>("pending");
  const [items, setItems] = useState<AccessRequestRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [actingId, setActingId] = useState<string | null>(null);
  const [toast, setToast] = useState<ToastMessage | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await adminService.listAccessRequests(
        filter === "all" ? undefined : filter,
      );
      setItems(data);
    } catch (e) {
      setToast({ kind: "error", text: getFriendlyErrorMessage(e) });
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [filter]);

  useEffect(() => {
    setLoading(true);
    void load();
  }, [load]);

  const approve = async (id: string) => {
    setActingId(id);
    try {
      await adminService.approveAccessRequest(id);
      setToast({ kind: "success", text: "Booking access granted" });
      await load();
    } catch (e) {
      setToast({ kind: "error", text: getFriendlyErrorMessage(e) });
    } finally {
      setActingId(null);
    }
  };

  const reject = async (id: string) => {
    setActingId(id);
    try {
      await adminService.rejectAccessRequest(id);
      setToast({ kind: "success", text: "Request rejected" });
      await load();
    } catch (e) {
      setToast({ kind: "error", text: getFriendlyErrorMessage(e) });
    } finally {
      setActingId(null);
    }
  };

  return (
    <SafeAreaView style={styles.container} edges={["top"]} testID="admin-access-requests-screen">
      <Toast message={toast} onHide={() => setToast(null)} />
      <ScreenHeader
        eyebrow="ADMIN"
        title="Access Requests"
        subtitle="Approve students who need booking access."
      />

      <View style={styles.filters}>
        {FILTERS.map((f) => (
          <Pressable
            key={f.key}
            style={[styles.chip, filter === f.key && styles.chipActive]}
            onPress={() => setFilter(f.key)}
            testID={`access-filter-${f.key}`}
          >
            <Text style={[styles.chipText, filter === f.key && styles.chipTextActive]}>{f.label}</Text>
          </Pressable>
        ))}
      </View>

      {loading ? (
        <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xl }} />
      ) : (
        <FlatList
          data={items}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.list}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} />
          }
          ListEmptyComponent={
            <EmptyState
              icon="star-outline"
              title="No requests"
              subtitle="Pending booking access requests will appear here."
            />
          }
          renderItem={({ item }) => (
            <Card style={styles.card} testID={`access-request-${item.id}`}>
              <Text style={styles.name}>{item.name}</Text>
              <Text style={styles.meta}>{item.email}</Text>
              <Text style={styles.meta}>Student ID: {item.student_id ?? "—"}</Text>
              {item.reason ? <Text style={styles.reason}>{item.reason}</Text> : null}
              <Text style={styles.status}>{item.status.toUpperCase()}</Text>
              {item.status === "pending" ? (
                <View style={styles.actions}>
                  <Button
                    label="Approve"
                    onPress={() => approve(item.id)}
                    loading={actingId === item.id}
                    disabled={actingId != null}
                    testID={`approve-${item.id}`}
                  />
                  <Button
                    label="Reject"
                    variant="secondary"
                    onPress={() => reject(item.id)}
                    loading={actingId === item.id}
                    disabled={actingId != null}
                    testID={`reject-${item.id}`}
                  />
                </View>
              ) : null}
            </Card>
          )}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  filters: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    marginBottom: spacing.sm,
  },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radii.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  chipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { ...typography.caption, color: colors.text_secondary, fontWeight: "700" },
  chipTextActive: { color: "#FFFFFF" },
  list: { padding: spacing.lg, paddingBottom: spacing.xxl, gap: spacing.md },
  card: { marginBottom: spacing.md, gap: spacing.xs },
  name: { ...typography.bodyBold, color: colors.text_primary },
  meta: { ...typography.caption, color: colors.text_secondary },
  reason: { ...typography.body, color: colors.text_primary, marginTop: spacing.xs },
  status: { ...typography.label, color: colors.text_tertiary, marginTop: spacing.sm },
  actions: { gap: spacing.sm, marginTop: spacing.md },
});
