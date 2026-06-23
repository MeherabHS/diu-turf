/** My Bookings — Phase 3. Upcoming / Completed / Cancelled tabs + live countdown. */
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import React, { useCallback, useMemo, useRef, useState } from "react";
import {
  FlatList,
  Modal,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";

import { Button } from "@/src/components/Button";
import { Card } from "@/src/components/Card";
import { EmptyState } from "@/src/components/EmptyState";
import { ErrorState } from "@/src/components/ErrorState";
import { ScreenHeader } from "@/src/components/ScreenHeader";
import { SkeletonList } from "@/src/components/Skeleton";
import { Toast, type ToastMessage } from "@/src/components/Toast";
import { useLiveScreenRefresh } from "@/src/hooks/useLiveScreenRefresh";
import { dhakaUtcMs, formatCountdown, useTicker } from "@/src/hooks/useTicker";
import { bookingService } from "@/src/services/bookingService";
import { cancelBookingReminders, presentInstantCancellation } from "@/src/services/notifications";
import { waitlistService } from "@/src/services/waitlistService";
import { useBookingsRefreshStore } from "@/src/store/useBookingsRefreshStore";
import { colors, radii, spacing, typography } from "@/src/theme";
import type { Booking, WaitlistEntry } from "@/src/types/booking";
import { prettyDate, prettyRange } from "@/src/utils/datetime";
import { getFriendlyErrorMessage } from "@/src/utils/errors";

type TabKey = "upcoming" | "waitlist" | "completed" | "cancelled";
const TABS: { key: TabKey; label: string }[] = [
  { key: "upcoming", label: "Upcoming" },
  { key: "waitlist", label: "Waitlist" },
  { key: "completed", label: "Completed" },
  { key: "cancelled", label: "Cancelled" },
];

function isFutureBooking(b: Booking): boolean {
  const startMs = dhakaUtcMs(b.booking_date, b.start_time);
  return Date.now() < startMs;
}
function isCompletedBooking(b: Booking): boolean {
  const endMs = dhakaUtcMs(b.booking_date, b.end_time);
  return b.status === "completed" || (b.status === "booked" && Date.now() >= endMs);
}

export default function BookingsScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const bumpBookingsRefresh = useBookingsRefreshStore((s) => s.bump);
  useTicker(1000);

  const [tab, setTab] = useState<TabKey>("upcoming");
  const [items, setItems] = useState<Booking[]>([]);
  const [waitlistItems, setWaitlistItems] = useState<WaitlistEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pendingCancel, setPendingCancel] = useState<Booking | null>(null);
  const [cancellingIds, setCancellingIds] = useState<Set<string>>(() => new Set());
  const cancellingIdsRef = useRef(cancellingIds);
  cancellingIdsRef.current = cancellingIds;

  const mergeServerItems = useCallback((data: Booking[], local: Booking[], pending: Set<string>) => {
    if (pending.size === 0) return data;
    return data.map((b) => {
      if (!pending.has(b.booking_id)) return b;
      const optimistic = local.find((p) => p.booking_id === b.booking_id);
      return optimistic ?? b;
    });
  }, []);

  const load = useCallback(async () => {
    try {
      const [bookings, waitlists] = await Promise.all([
        bookingService.mine(),
        waitlistService.mine(),
      ]);
      setItems((prev) => mergeServerItems(bookings, prev, cancellingIdsRef.current));
      setWaitlistItems(waitlists.filter((w) => w.status === "waiting"));
      setLoadError(null);
    } catch (e) {
      setLoadError(getFriendlyErrorMessage(e, "Unable to load. Try again."));
      setToast({ kind: "error", text: getFriendlyErrorMessage(e) });
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [mergeServerItems]);
  useLiveScreenRefresh(load);

  const filtered = useMemo(() => {
    if (tab === "waitlist") return waitlistItems;
    if (tab === "upcoming") return items.filter((b) => b.status === "booked" && isFutureBooking(b));
    if (tab === "cancelled") return items.filter((b) => b.status === "cancelled");
    return items.filter((b) => isCompletedBooking(b));
  }, [items, waitlistItems, tab]);

  const counts = useMemo(() => ({
    upcoming: items.filter((b) => b.status === "booked" && isFutureBooking(b)).length,
    waitlist: waitlistItems.length,
    completed: items.filter(isCompletedBooking).length,
    cancelled: items.filter((b) => b.status === "cancelled").length,
  }), [items, waitlistItems]);

  const doCancel = async () => {
    if (!pendingCancel) return;
    const target = pendingCancel;
    const bookingId = target.booking_id;
    const previousItems = items;
    const nowIso = new Date().toISOString();

    setCancellingIds((prev) => new Set(prev).add(bookingId));
    setItems((prev) =>
      prev.map((b) =>
        b.booking_id === bookingId
          ? { ...b, status: "cancelled" as const, updated_at: nowIso }
          : b,
      ),
    );
    setPendingCancel(null);

    try {
      await bookingService.cancel(bookingId);
      cancelBookingReminders(bookingId).catch(() => undefined);
      presentInstantCancellation(target).catch(() => undefined);
      setToast({ kind: "success", text: "Booking cancelled" });
      void bookingService.mine().then((data) => setItems(data)).catch(() => undefined);
      bumpBookingsRefresh();
    } catch (e) {
      setItems(previousItems);
      setToast({ kind: "error", text: getFriendlyErrorMessage(e) });
    } finally {
      setCancellingIds((prev) => {
        const next = new Set(prev);
        next.delete(bookingId);
        return next;
      });
    }
  };

  const isCancelling = (bookingId: string) => cancellingIds.has(bookingId);

  type ListRow =
    | { kind: "waitlist"; entry: WaitlistEntry }
    | { kind: "booking"; booking: Booking };

  const listData = useMemo((): ListRow[] => {
    if (tab === "waitlist") {
      return waitlistItems.map((entry) => ({ kind: "waitlist", entry }));
    }
    return (filtered as Booking[]).map((booking) => ({ kind: "booking", booking }));
  }, [tab, filtered, waitlistItems]);

  const listEmpty = useMemo(() => {
    if (loading) return <SkeletonList count={4} />;
    if (loadError && items.length === 0) {
      return (
        <ErrorState
          message={loadError}
          onRetry={() => {
            setLoading(true);
            setLoadError(null);
            load();
          }}
          testID="bookings-load-error"
        />
      );
    }
    return (
      <EmptyState
        icon="calendar-outline"
        title={
          tab === "upcoming"
            ? "No upcoming bookings"
            : tab === "waitlist"
              ? "No waitlist entries"
              : tab === "cancelled"
                ? "No cancelled bookings"
                : "No completed bookings"
        }
        subtitle={
          tab === "upcoming"
            ? "Book a slot to see it here."
            : tab === "waitlist"
              ? "Join a waitlist when a slot is full on the Book tab."
              : "Your history will appear here."
        }
        actionLabel={tab === "upcoming" ? "Book a slot" : undefined}
        onAction={tab === "upcoming" ? () => router.push("/(tabs)/book") : undefined}
        testID={`bookings-empty-${tab}`}
      />
    );
  }, [loading, loadError, items.length, tab, load, router]);

  return (
    <SafeAreaView style={styles.container} edges={["top"]} testID="bookings-screen">
      <Toast message={toast} onHide={() => setToast(null)} />
      <ScreenHeader eyebrow="MY BOOKINGS" title="Your reservations" />

      {/* Tabs */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.tabsRow}
        style={styles.tabsBar}
      >
        {TABS.map((t) => (
          <TouchableOpacity
            key={t.key}
            onPress={() => setTab(t.key)}
            style={[styles.tab, tab === t.key && styles.tabActive]}
            testID={`bookings-tab-${t.key}`}
            activeOpacity={0.8}
          >
            <Text style={[styles.tabLabel, tab === t.key && styles.tabLabelActive]}>
              {t.label}
            </Text>
            <View style={[styles.tabBadge, tab === t.key && styles.tabBadgeActive]}>
              <Text style={[styles.tabBadgeText, tab === t.key && styles.tabBadgeTextActive]}>
                {counts[t.key]}
              </Text>
            </View>
          </TouchableOpacity>
        ))}
      </ScrollView>

      <FlatList
        data={listData}
        keyExtractor={(row) =>
          row.kind === "waitlist" ? row.entry.waitlist_id : row.booking.booking_id
        }
        renderItem={({ item: row }) =>
          row.kind === "waitlist" ? (
            <WaitlistCard entry={row.entry} />
          ) : (
            <BookingCard
              booking={row.booking}
              showCancel={tab === "upcoming"}
              cancelDisabled={isCancelling(row.booking.booking_id)}
              onCancel={() => setPendingCancel(row.booking)}
            />
          )
        }
        contentContainerStyle={[
          styles.scroll,
          { paddingBottom: insets.bottom + spacing.xxl },
          listData.length === 0 && styles.scrollEmpty,
        ]}
        ListEmptyComponent={listEmpty}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={colors.primary} />
        }
      />

      <Modal
        visible={!!pendingCancel}
        transparent
        animationType="fade"
        onRequestClose={() => {
          if (!pendingCancel || !isCancelling(pendingCancel.booking_id)) {
            setPendingCancel(null);
          }
        }}
      >
        <View style={styles.modalBackdrop} testID="cancel-modal">
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>Cancel booking?</Text>
            {pendingCancel ? (
              <>
                <View style={styles.modalRow}>
                  <Text style={styles.modalRowLabel}>DATE</Text>
                  <Text style={styles.modalRowValue}>{prettyDate(pendingCancel.booking_date)}</Text>
                </View>
                <View style={styles.modalRow}>
                  <Text style={styles.modalRowLabel}>TIME</Text>
                  <Text style={styles.modalRowValue}>{prettyRange(pendingCancel.start_time, pendingCancel.end_time)}</Text>
                </View>
              </>
            ) : null}
            <View style={{ height: spacing.lg }} />
            <Button
              label="Yes, cancel"
              loadingLabel="Cancelling..."
              variant="secondary"
              onPress={doCancel}
              loading={pendingCancel ? isCancelling(pendingCancel.booking_id) : false}
              testID="cancel-modal-confirm"
            />
            <View style={{ height: spacing.sm }} />
            <Button
              label="Keep booking"
              variant="ghost"
              onPress={() => setPendingCancel(null)}
              disabled={pendingCancel ? isCancelling(pendingCancel.booking_id) : false}
              testID="cancel-modal-keep"
            />
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const WaitlistCard: React.FC<{ entry: WaitlistEntry }> = ({ entry }) => (
  <Card style={{ marginTop: spacing.md }} testID={`waitlist-card-${entry.waitlist_id}`}>
    <View style={styles.cardTop}>
      <View>
        <Text style={styles.cardDate}>{prettyDate(entry.booking_date)}</Text>
        <Text style={styles.cardTime}>{prettyRange(entry.start_time, entry.end_time)}</Text>
        <Text style={styles.slotMeta}>{entry.slot_label}</Text>
      </View>
      <View style={[styles.statusPill, styles.waitlistPill]}>
        <Text style={[styles.statusText, styles.waitlistPillText]}>WAITLISTED</Text>
      </View>
    </View>
    <Text style={styles.queueLine}>Position in Queue: #{entry.position}</Text>
    <Text style={styles.createdAt}>
      Joined {new Date(entry.created_at).toLocaleString()}
    </Text>
  </Card>
);

const BookingCard: React.FC<{
  booking: Booking;
  showCancel?: boolean;
  cancelDisabled?: boolean;
  onCancel?: () => void;
}> = ({
  booking, showCancel, cancelDisabled, onCancel,
}) => {
  const startMs = dhakaUtcMs(booking.booking_date, booking.start_time);
  const endMs = dhakaUtcMs(booking.booking_date, booking.end_time);
  const now = Date.now();

  const cd =
    booking.status === "cancelled" ? null :
    now < startMs ? `Starts in ${formatCountdown(startMs - now)}` :
    now < endMs ? `Ends in ${formatCountdown(endMs - now)}` :
    "Completed";

  const statusColor =
    booking.status === "cancelled" ? colors.danger :
    isCompletedBooking(booking) ? colors.text_tertiary :
    colors.status_available;
  const statusBg =
    booking.status === "cancelled" ? colors.danger_bg :
    isCompletedBooking(booking) ? colors.surface_secondary :
    colors.status_available_bg;
  const statusLabel =
    booking.status === "cancelled" ? "CANCELLED" :
    isCompletedBooking(booking) ? "COMPLETED" : "BOOKED";

  return (
    <Card style={{ marginTop: spacing.md }} testID={`booking-card-${booking.booking_id}`}>
      <View style={styles.cardTop}>
        <View>
          <Text style={styles.cardDate}>{prettyDate(booking.booking_date)}</Text>
          <Text style={styles.cardTime}>{prettyRange(booking.start_time, booking.end_time)}</Text>
        </View>
        <View style={[styles.statusPill, { backgroundColor: statusBg }]}>
          <Text style={[styles.statusText, { color: statusColor }]}>{statusLabel}</Text>
        </View>
      </View>
      {cd ? <Text style={styles.countdown}>{cd}</Text> : null}
      <Text style={styles.createdAt}>
        Created {new Date(booking.created_at).toLocaleString()}
      </Text>
      {showCancel ? (
        <View style={{ marginTop: spacing.md }}>
          <Button
            label="Cancel booking"
            loadingLabel="Cancelling..."
            variant="secondary"
            onPress={onCancel}
            disabled={cancelDisabled}
            loading={cancelDisabled}
            testID={`booking-cancel-${booking.booking_id}`}
          />
        </View>
      ) : null}
    </Card>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  tabsBar: { maxHeight: 56, borderBottomWidth: 1, borderBottomColor: colors.border, flexGrow: 0 },
  tabsRow: { paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, gap: spacing.sm, alignItems: "center" },
  tab: {
    flexDirection: "row", alignItems: "center", gap: spacing.xs,
    height: 36, paddingHorizontal: spacing.md,
    borderRadius: radii.pill,
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
    flexShrink: 0,
  },
  tabActive: { backgroundColor: colors.text_primary, borderColor: colors.text_primary },
  tabLabel: { ...typography.bodyBold, fontSize: 13, color: colors.text_primary },
  tabLabelActive: { color: "#FFFFFF" },
  tabBadge: { backgroundColor: colors.surface_secondary, borderRadius: radii.pill, paddingHorizontal: 8, paddingVertical: 2 },
  tabBadgeActive: { backgroundColor: "rgba(255,255,255,0.18)" },
  tabBadgeText: { ...typography.label, fontSize: 10, color: colors.text_secondary },
  tabBadgeTextActive: { color: "#FFFFFF" },

  scroll: { paddingHorizontal: spacing.lg, paddingTop: spacing.sm },
  scrollEmpty: { flexGrow: 1 },
  empty: { alignItems: "center", gap: spacing.sm, paddingVertical: spacing.md },
  emptyTitle: { ...typography.h3, color: colors.text_primary },
  emptySub: { ...typography.body, color: colors.text_secondary, textAlign: "center" },
  cardTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  cardDate: { ...typography.bodyBold, color: colors.text_primary },
  cardTime: { ...typography.h3, color: colors.text_primary, marginTop: 2 },
  countdown: { ...typography.bodyBold, color: colors.text_primary, marginTop: spacing.sm, fontVariant: ["tabular-nums"] },
  createdAt: { ...typography.caption, marginTop: spacing.sm },
  slotMeta: { ...typography.caption, marginTop: 4 },
  queueLine: { ...typography.bodyBold, color: "#B45309", marginTop: spacing.sm },
  waitlistPill: { backgroundColor: "#FEF3C7" },
  waitlistPillText: { color: "#B45309" },
  statusPill: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: radii.pill },
  statusText: { ...typography.label, fontSize: 10 },
  modalBackdrop: { flex: 1, backgroundColor: "rgba(15,23,42,0.55)", justifyContent: "center", padding: spacing.lg },
  modalCard: { backgroundColor: colors.background, borderRadius: radii.lg, padding: spacing.lg },
  modalTitle: { ...typography.h2, color: colors.text_primary, marginBottom: spacing.lg },
  modalRow: { flexDirection: "row", justifyContent: "space-between", paddingVertical: spacing.sm },
  modalRowLabel: { ...typography.label, color: colors.text_secondary },
  modalRowValue: { ...typography.bodyBold, color: colors.text_primary, maxWidth: "70%", textAlign: "right" },
});
