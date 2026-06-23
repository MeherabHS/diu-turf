/** Home tab — student-focused booking overview. */
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import React, { useCallback, useMemo, useState } from "react";
import {
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";

import { BookingAccessBanner } from "@/src/components/BookingAccessBanner";
import { Button } from "@/src/components/Button";
import { Card } from "@/src/components/Card";
import { EmptyState } from "@/src/components/EmptyState";
import { ErrorState } from "@/src/components/ErrorState";
import { SkeletonCard, SkeletonList } from "@/src/components/Skeleton";
import { useLiveScreenRefresh } from "@/src/hooks/useLiveScreenRefresh";
import { useOnline } from "@/src/hooks/useOnline";
import { useSlowLoading } from "@/src/hooks/useSlowLoading";
import { dhakaUtcMs, formatCountdown, useTicker } from "@/src/hooks/useTicker";
import { activityService } from "@/src/services/activityService";
import { bookingService } from "@/src/services/bookingService";
import { useAuthStore } from "@/src/store/useAuthStore";
import { colors, radii, spacing, typography } from "@/src/theme";
import type { ActivityItem, Booking, DateOverview, SlotView } from "@/src/types/booking";
import {
  formatActivityWhen,
  prettyDate,
  prettyRange,
  timeOfDayGreeting,
  todayDhakaDateString,
} from "@/src/utils/datetime";
import { getFriendlyErrorMessage } from "@/src/utils/errors";
import { getActivityDisplayText, isMeaningfulActivity } from "@/src/utils/activityText";
import { displayName, profileSubtext } from "@/src/utils/userDisplay";
import { canBookSlots } from "@/src/utils/roles";

function isFutureBooking(b: Booking): boolean {
  return Date.now() < dhakaUtcMs(b.booking_date, b.start_time);
}

function isCompletedBooking(b: Booking): boolean {
  const endMs = dhakaUtcMs(b.booking_date, b.end_time);
  return b.status === "completed" || (b.status === "booked" && Date.now() >= endMs);
}

export default function HomeScreen() {
  const user = useAuthStore((s) => s.user);
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const online = useOnline();
  useTicker(1000);

  const today = todayDhakaDateString();
  const [overview, setOverview] = useState<DateOverview | null>(null);
  const [myBookings, setMyBookings] = useState<Booking[]>([]);
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const slowLoading = useSlowLoading(loading && myBookings.length === 0);

  const load = useCallback(async () => {
    try {
      const [ov, mine, recent] = await Promise.all([
        bookingService.forDate(today),
        bookingService.mine(),
        activityService.recent(5),
      ]);
      setOverview(ov);
      setMyBookings(mine);
      setActivity(recent);
      setLoadError(null);
    } catch (e) {
      setLoadError(getFriendlyErrorMessage(e, "Unable to load. Try again."));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [today]);

  useLiveScreenRefresh(load);

  const headerName = displayName(user);
  const headerSub = profileSubtext(user);
  const canBook = canBookSlots(user?.role);
  const greeting = timeOfDayGreeting();
  const visibleActivity = useMemo(
    () => activity.filter(isMeaningfulActivity),
    [activity],
  );

  const upcomingBooking = useMemo(
    () =>
      myBookings
        .filter((b) => b.status === "booked" && isFutureBooking(b))
        .sort(
          (a, b) =>
            dhakaUtcMs(a.booking_date, a.start_time) - dhakaUtcMs(b.booking_date, b.start_time),
        )[0] ?? null,
    [myBookings],
  );

  const stats = useMemo(
    () => ({
      total: myBookings.length,
      completed: myBookings.filter(isCompletedBooking).length,
      cancelled: myBookings.filter((b) => b.status === "cancelled").length,
    }),
    [myBookings],
  );

  return (
    <SafeAreaView style={styles.container} edges={["top"]} testID="home-screen">
      <View style={styles.header} testID="home-header">
        <Text style={styles.greeting}>{greeting} 👋</Text>
        <Text style={styles.studentId}>{headerName}</Text>
        {headerSub ? <Text style={styles.headerMeta}>{headerSub}</Text> : null}
        <Text style={styles.headerSub}>
          Manage your turf reservations and upcoming sessions.
        </Text>
      </View>

      {!online ? (
        <View style={styles.offlineBanner} testID="offline-banner">
          <Ionicons name="cloud-offline-outline" size={16} color={colors.danger} />
          <Text style={styles.offlineText}>You&apos;re offline or the server is unreachable.</Text>
        </View>
      ) : null}

      {loadError && !loading && myBookings.length === 0 && !overview ? (
        <View style={{ paddingHorizontal: spacing.lg, marginTop: spacing.sm }}>
          <ErrorState
            message={loadError}
            hint={slowLoading ? "Still loading..." : undefined}
            onRetry={() => {
              setLoading(true);
              setLoadError(null);
              load();
            }}
            testID="home-load-error"
          />
        </View>
      ) : null}

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
        <BookingStatusCard
          booking={upcomingBooking}
          loading={loading && myBookings.length === 0}
          canBook={canBook}
          onViewBooking={() => router.push("/(tabs)/bookings")}
          onBookSlot={() => router.push(canBook ? "/(tabs)/book" : "/request-access")}
        />

        {!canBook ? <BookingAccessBanner /> : null}

        <Text style={styles.sectionTitle}>Today&apos;s Turf Schedule</Text>
        {loading && !overview ? (
          <SkeletonList count={3} />
        ) : (
          <View style={styles.scheduleList}>
            {overview?.slots.map((s) => <ScheduleSlotRow key={s.slot_id} slot={s} />)}
          </View>
        )}

        <StatsCard stats={stats} loading={loading && myBookings.length === 0} />

        <View style={styles.activityHeader}>
          <Text style={styles.sectionTitle}>Your booking updates</Text>
          {visibleActivity.length > 0 ? (
            <TouchableOpacity onPress={() => router.push("/activity")} testID="home-activity-see-all">
              <Text style={styles.seeAll}>See all</Text>
            </TouchableOpacity>
          ) : null}
        </View>

        {loading && visibleActivity.length === 0 ? (
          <SkeletonList count={2} />
        ) : visibleActivity.length === 0 ? (
          <EmptyState
            icon="pulse-outline"
            title="No recent activity yet"
            subtitle="Your booking updates will appear here."
            testID="home-activity-empty"
          />
        ) : (
          visibleActivity.map((item) => (
            <ActivityPreviewRow key={item.activity_id} item={item} />
          ))
        )}

        <TouchableOpacity
          style={styles.quickRow}
          onPress={() => router.push("/notifications")}
          testID="home-quick-notifications"
          activeOpacity={0.85}
        >
          <Ionicons name="notifications-outline" size={20} color={colors.text_primary} />
          <Text style={styles.quickLabel}>Notifications</Text>
          <Ionicons name="chevron-forward" size={18} color={colors.text_tertiary} />
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

const BookingStatusCard: React.FC<{
  booking: Booking | null;
  loading: boolean;
  canBook: boolean;
  onViewBooking: () => void;
  onBookSlot: () => void;
}> = ({ booking, loading, canBook, onViewBooking, onBookSlot }) => {
  const startMs = booking ? dhakaUtcMs(booking.booking_date, booking.start_time) : 0;
  const countdown = booking && startMs > Date.now()
    ? `Starts in ${formatCountdown(startMs - Date.now())}`
    : null;

  return (
    <Card testID="booking-status-card" style={styles.primaryCard}>
      <Text style={styles.cardEyebrow}>Your Booking Status</Text>
      {loading ? (
        <SkeletonCard lines={4} testID="booking-status-skeleton" />
      ) : booking ? (
        <>
          <View style={styles.statusRow}>
            <Ionicons name="checkmark-circle" size={22} color={colors.status_available} />
            <Text style={styles.statusHeadline}>Upcoming Booking</Text>
          </View>
          <Text style={styles.bookingDate}>{prettyDate(booking.booking_date)}</Text>
          <Text style={styles.bookingTime}>{prettyRange(booking.start_time, booking.end_time)}</Text>
          {countdown ? (
            <Text style={styles.countdown} testID="home-upcoming-countdown">{countdown}</Text>
          ) : null}
          <View style={{ height: spacing.md }} />
          <Button label="View Booking" onPress={onViewBooking} testID="home-view-booking" />
        </>
      ) : (
        <>
          <Text style={styles.statusHeadline}>No Active Booking</Text>
          <Text style={styles.emptyBookingSub}>
            {canBook
              ? "Reserve a slot and secure your play time."
              : "Browse turf availability. Request booking access to reserve a slot."}
          </Text>
          <View style={{ height: spacing.md }} />
          {canBook ? (
            <Button label="Book a Slot" onPress={onBookSlot} testID="home-book-slot-primary" />
          ) : (
            <Button
              label="Request Booking Access"
              onPress={onBookSlot}
              variant="secondary"
              testID="home-request-access-primary"
            />
          )}
        </>
      )}
    </Card>
  );
};

const StatsCard: React.FC<{
  stats: { total: number; completed: number; cancelled: number };
  loading: boolean;
}> = ({ stats, loading }) => (
  <Card testID="stats-card" style={styles.statsCard}>
    <Text style={styles.cardEyebrow}>Your Statistics</Text>
    <View style={styles.statsGrid}>
      <StatItem label="Total Bookings" value={loading ? "—" : String(stats.total)} />
      <StatItem label="Completed Sessions" value={loading ? "—" : String(stats.completed)} />
      <StatItem label="Cancelled" value={loading ? "—" : String(stats.cancelled)} />
    </View>
  </Card>
);

const StatItem: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <View style={styles.statItem}>
    <Text style={styles.statValue}>{value}</Text>
    <Text style={styles.statLabel}>{label}</Text>
  </View>
);

const ScheduleSlotRow: React.FC<{ slot: SlotView }> = ({ slot }) => {
  const now = Date.now();
  const endMs = dhakaUtcMs(slot.booking_date, slot.end_time);
  const finished = slot.status === "completed" || now >= endMs;

  const statusLabel = finished
    ? "Finished"
    : slot.status === "available"
      ? "Available"
      : slot.status === "maintenance"
        ? "Unavailable"
        : "Booked";

  const tone = finished ? "finished" : slot.status === "available" ? "available" : slot.status === "maintenance" ? "finished" : "booked";

  return (
    <View
      style={[
        styles.scheduleRow,
        tone === "available" && styles.scheduleAvailable,
        tone === "booked" && styles.scheduleBooked,
        tone === "finished" && styles.scheduleFinished,
      ]}
      testID={`live-slot-${slot.slot_id}`}
    >
      <Text style={styles.scheduleTime}>{prettyRange(slot.start_time, slot.end_time)}</Text>
      <View style={[
        styles.schedulePill,
        tone === "available" && styles.pillAvailable,
        tone === "booked" && styles.pillBooked,
        tone === "finished" && styles.pillFinished,
      ]}>
        <Text style={[
          styles.scheduleStatus,
          tone === "available" && styles.textAvailable,
          tone === "booked" && styles.textBooked,
          tone === "finished" && styles.textFinished,
        ]}>
          {statusLabel}
        </Text>
      </View>
    </View>
  );
};

const ActivityPreviewRow: React.FC<{ item: ActivityItem }> = ({ item }) => {
  const text = getActivityDisplayText(item);
  if (!text) return null;
  const positive = item.action === "BOOKED" || item.action === "COMPLETED";
  return (
    <View style={styles.activityRow} testID={`home-activity-${item.activity_id}`}>
      <Ionicons
        name={positive ? "checkmark-circle" : "close-circle"}
        size={20}
        color={positive ? colors.status_available : colors.danger}
        style={{ marginTop: 1 }}
      />
      <View style={{ flex: 1 }}>
        <Text style={styles.activityTitle} numberOfLines={2}>{text}</Text>
        <Text style={styles.activityWhen}>{formatActivityWhen(item.created_at)}</Text>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  header: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.lg,
    paddingBottom: spacing.md,
    backgroundColor: colors.background,
  },
  greeting: { ...typography.h2, color: colors.text_primary },
  studentId: { ...typography.h3, color: colors.text_primary, marginTop: spacing.xs },
  headerMeta: { ...typography.bodyBold, color: colors.text_secondary, marginTop: 4 },
  headerSub: { ...typography.body, color: colors.text_secondary, marginTop: spacing.sm },
  scroll: { paddingHorizontal: spacing.lg, paddingTop: spacing.xs, gap: spacing.md },
  offlineBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    backgroundColor: colors.danger_bg,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.lg,
  },
  offlineText: { ...typography.caption, color: colors.danger, fontWeight: "600" },
  primaryCard: { marginTop: spacing.xs },
  cardEyebrow: { ...typography.label, color: colors.text_secondary, marginBottom: spacing.sm },
  statusRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  statusHeadline: { ...typography.h3, color: colors.text_primary },
  bookingDate: { ...typography.bodyBold, color: colors.text_primary, marginTop: spacing.sm },
  bookingTime: { ...typography.body, color: colors.text_secondary, marginTop: 4 },
  countdown: {
    ...typography.bodyBold,
    color: colors.primary,
    marginTop: spacing.sm,
    fontVariant: ["tabular-nums"],
  },
  emptyBookingSub: { ...typography.body, color: colors.text_secondary, marginTop: spacing.sm },
  sectionTitle: {
    ...typography.bodyBold,
    fontSize: 18,
    color: colors.text_primary,
    marginTop: spacing.sm,
  },
  scheduleList: { gap: spacing.sm },
  scheduleRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingVertical: spacing.sm + 2,
    paddingHorizontal: spacing.md,
    backgroundColor: colors.surface,
  },
  scheduleAvailable: { borderColor: colors.status_available, backgroundColor: colors.status_available_bg },
  scheduleBooked: { borderColor: "#BFDBFE", backgroundColor: "#EFF6FF" },
  scheduleFinished: { backgroundColor: colors.surface_secondary, opacity: 0.85 },
  scheduleTime: { ...typography.bodyBold, color: colors.text_primary },
  schedulePill: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: radii.pill },
  pillAvailable: { backgroundColor: colors.status_available_bg },
  pillBooked: { backgroundColor: "#DBEAFE" },
  pillFinished: { backgroundColor: colors.surface_secondary },
  scheduleStatus: { ...typography.label, fontSize: 10 },
  textAvailable: { color: colors.status_available },
  textBooked: { color: "#2563EB" },
  textFinished: { color: colors.text_tertiary },
  statsCard: { paddingVertical: spacing.md },
  statsGrid: {
    flexDirection: "row",
    justifyContent: "space-between",
    gap: spacing.sm,
    marginTop: spacing.sm,
  },
  statItem: { flex: 1, alignItems: "center" },
  statValue: { ...typography.h3, color: colors.text_primary },
  statLabel: { ...typography.caption, textAlign: "center", marginTop: 4 },
  cta: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.primary,
    borderRadius: radii.lg,
    padding: spacing.lg,
    marginTop: spacing.sm,
  },
  ctaTitle: { ...typography.h3, color: "#FFFFFF" },
  ctaSub: { ...typography.caption, color: "#FFFFFF", opacity: 0.9, marginTop: 4 },
  activityHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: spacing.sm,
  },
  seeAll: { ...typography.bodyBold, color: colors.primary, fontSize: 14 },
  emptyActivity: { ...typography.body, color: colors.text_secondary, textAlign: "center" },
  activityRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: spacing.md,
    paddingVertical: spacing.sm + 2,
    paddingHorizontal: spacing.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
  },
  activityTitle: { ...typography.bodyBold, color: colors.text_primary },
  activityWhen: { ...typography.caption, marginTop: 2 },
  quickRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    marginTop: spacing.sm,
  },
  quickLabel: { ...typography.bodyBold, color: colors.text_primary, flex: 1 },
});
