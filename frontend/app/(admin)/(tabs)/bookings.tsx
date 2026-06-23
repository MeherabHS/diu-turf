/** Admin > Bookings — paginated reservations across all students. */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { FlatList, RefreshControl, StyleSheet, Text, View } from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";

import { Button } from "@/src/components/Button";
import { EmptyState } from "@/src/components/EmptyState";
import { ErrorState } from "@/src/components/ErrorState";
import { ScreenHeader } from "@/src/components/ScreenHeader";
import { SkeletonList } from "@/src/components/Skeleton";
import { useLiveScreenRefresh } from "@/src/hooks/useLiveScreenRefresh";
import { adminService, type AdminBookingRow } from "@/src/services/adminService";
import { colors, radii, spacing, typography } from "@/src/theme";
import { getFriendlyErrorMessage } from "@/src/utils/errors";

const PAGE_SIZE = 20;

export default function AdminBookingsScreen() {
  const insets = useSafeAreaInsets();
  const [items, setItems] = useState<AdminBookingRow[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const totalPages = useMemo(() => Math.max(1, Math.ceil(total / PAGE_SIZE)), [total]);

  const load = useCallback(async () => {
    try {
      const data = await adminService.listBookings({ page, page_size: PAGE_SIZE });
      setItems(data.items);
      setTotal(data.total);
      setLoadError(null);
    } catch (e) {
      setLoadError(getFriendlyErrorMessage(e, "Unable to load. Try again."));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [page]);

  useLiveScreenRefresh(load);

  useEffect(() => {
    setLoading(true);
    load();
  }, [load]);

  const listEmpty = useMemo(() => {
    if (loading && items.length === 0) {
      return <SkeletonList count={5} />;
    }
    if (loadError && items.length === 0) {
      return (
        <ErrorState
          message={loadError}
          onRetry={() => {
            setLoading(true);
            load();
          }}
          testID="admin-bookings-error"
        />
      );
    }
    if (items.length === 0) {
      return (
        <EmptyState
          icon="calendar-outline"
          title="No bookings for this date"
          subtitle="When students reserve slots, they will appear here."
          testID="admin-bookings-empty"
        />
      );
    }
    return null;
  }, [loading, items.length, loadError, load]);

  const listFooter = useMemo(() => {
    if (totalPages <= 1) return null;
    return (
      <View style={styles.pagination}>
        <Button
          label="Previous"
          variant="secondary"
          onPress={() => setPage((p) => Math.max(1, p - 1))}
          disabled={page <= 1 || loading}
          testID="admin-bookings-prev"
          fullWidth={false}
          style={styles.pageBtn}
        />
        <Text style={styles.pageLabel}>Page {page} of {totalPages}</Text>
        <Button
          label="Next"
          variant="secondary"
          onPress={() => setPage((p) => Math.min(totalPages, p + 1))}
          disabled={page >= totalPages || loading}
          testID="admin-bookings-next"
          fullWidth={false}
          style={styles.pageBtn}
        />
      </View>
    );
  }, [totalPages, page, loading]);

  return (
    <SafeAreaView style={styles.container} edges={["top"]} testID="admin-bookings-screen">
      <ScreenHeader
        eyebrow="ADMIN · BOOKINGS"
        title="All bookings"
        subtitle="Recent reservations · newest first"
      />
      <FlatList
        data={items}
        keyExtractor={(b) => b.booking_id}
        renderItem={({ item: b }) => (
          <View style={styles.row} testID={`admin-booking-${b.booking_id}`}>
            <Text style={styles.primary}>
              {b.booking_date} · {b.slot_label} · {b.time_range}
            </Text>
            <Text style={styles.secondary}>
              {b.student_name} ({b.student_id ?? b.student_email})
            </Text>
            <Text style={styles.meta}>{b.status.toUpperCase()}</Text>
          </View>
        )}
        contentContainerStyle={[
          styles.scroll,
          { paddingBottom: insets.bottom + spacing.xxl },
          items.length === 0 && styles.scrollEmpty,
        ]}
        ListEmptyComponent={listEmpty}
        ListFooterComponent={listFooter}
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
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  scroll: { paddingHorizontal: spacing.lg, paddingTop: spacing.sm },
  scrollEmpty: { flexGrow: 1 },
  row: {
    backgroundColor: colors.surface,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    gap: 4,
    marginBottom: spacing.sm,
  },
  primary: { ...typography.bodyBold, color: colors.text_primary, fontSize: 14 },
  secondary: { ...typography.body, color: colors.text_secondary },
  meta: { ...typography.caption, color: colors.text_tertiary },
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
