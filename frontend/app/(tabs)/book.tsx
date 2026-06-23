/** Book screen — swipeable dates, smooth scroll, clear navigation. */
import { Ionicons } from "@expo/vector-icons";
import { useNavigation, useRouter } from "expo-router";
import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Modal,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";

import { BookingAccessBanner } from "@/src/components/BookingAccessBanner";
import { Button } from "@/src/components/Button";
import { BookingCalendar } from "@/src/components/BookingCalendar";
import { ErrorState } from "@/src/components/ErrorState";
import { SkeletonSlotCards } from "@/src/components/Skeleton";
import { Toast, type ToastMessage } from "@/src/components/Toast";
import { useLiveScreenRefresh } from "@/src/hooks/useLiveScreenRefresh";
import { useSlowLoading } from "@/src/hooks/useSlowLoading";
import { usageService } from "@/src/services/activityService";
import { bookingService } from "@/src/services/bookingService";
import {
  presentInstantConfirmation,
  presentWaitlistJoined,
  scheduleBookingReminders,
} from "@/src/services/notifications";
import { waitlistService } from "@/src/services/waitlistService";
import { useBookingsRefreshStore } from "@/src/store/useBookingsRefreshStore";
import { useAuthStore } from "@/src/store/useAuthStore";
import { colors, spacing, typography } from "@/src/theme";
import type { CalendarDay, DateOverview, SlotId, SlotView } from "@/src/types/booking";
import { formatBookerBookedText } from "@/src/utils/userDisplay";
import { getFriendlyErrorMessage } from "@/src/utils/errors";
import { canBookSlots } from "@/src/utils/roles";
import {
  parseYearMonth,
  prettyDateLong,
  prettyRange,
  todayDhakaDateString,
} from "@/src/utils/datetime";

const CARD_RADIUS = 16;
const TAB_BAR_CLEARANCE = 72;

type SlotVisual = "available" | "mine" | "unavailable";

function slotVisual(slot: SlotView): SlotVisual {
  if (slot.status === "available") return "available";
  if (slot.is_mine && slot.status === "booked") return "mine";
  return "unavailable";
}

function availabilityLabel(count: number, date: string, today: string): string {
  const noun = count === 1 ? "slot" : "slots";
  if (date === today) return `${count} ${noun} available today`;
  return `${count} ${noun} available`;
}

export default function BookScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const navigation = useNavigation();
  const bumpRefresh = useBookingsRefreshStore((s) => s.bump);
  const user = useAuthStore((s) => s.user);
  const canBook = canBookSlots(user?.role);
  const today = todayDhakaDateString();
  const initialYm = parseYearMonth(today);
  const [date, setDate] = useState(today);
  const [viewYear, setViewYear] = useState(initialYm.year);
  const [viewMonth, setViewMonth] = useState(initialYm.month);
  const [calendarDays, setCalendarDays] = useState<CalendarDay[]>([]);
  const [calendarLoading, setCalendarLoading] = useState(true);
  const [overview, setOverview] = useState<DateOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [pendingSlot, setPendingSlot] = useState<SlotView | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [joiningSlotId, setJoiningSlotId] = useState<SlotId | null>(null);
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showUpdatedHint, setShowUpdatedHint] = useState(false);
  const overviewRef = useRef(overview);
  overviewRef.current = overview;
  const updatedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const slowLoading = useSlowLoading(loading && !overview);

  const markUpdated = useCallback(() => {
    setShowUpdatedHint(true);
    if (updatedTimer.current) clearTimeout(updatedTimer.current);
    updatedTimer.current = setTimeout(() => setShowUpdatedHint(false), 4000);
  }, []);

  useEffect(() => () => {
    if (updatedTimer.current) clearTimeout(updatedTimer.current);
  }, []);

  const loadCalendar = useCallback(async (year: number, month: number) => {
    try {
      const data = await usageService.calendar(year, month);
      setCalendarDays(data.days);
    } catch {
      /* keep last calendar */
    } finally {
      setCalendarLoading(false);
    }
  }, []);

  const loadSlots = useCallback(async (target: string) => {
    try {
      const data = await bookingService.forDate(target);
      setOverview(data);
      setLoadError(null);
      markUpdated();
    } catch (e) {
      setLoadError(getFriendlyErrorMessage(e, "Unable to load. Try again."));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [markUpdated]);

  const refreshAll = useCallback(() => {
    void Promise.all([
      loadCalendar(viewYear, viewMonth),
      loadSlots(date),
    ]);
  }, [loadCalendar, loadSlots, viewYear, viewMonth, date]);

  useLiveScreenRefresh(refreshAll);

  useEffect(() => {
    setCalendarLoading(true);
    loadCalendar(viewYear, viewMonth);
  }, [viewYear, viewMonth, loadCalendar]);

  useEffect(() => {
    setLoading(true);
    loadSlots(date);
  }, [date, loadSlots]);

  const selectDate = useCallback(
    (nextDate: string) => {
      if (nextDate < today) return;
      setDate(nextDate);
      setLoading(true);
      const ym = parseYearMonth(nextDate);
      if (ym.year !== viewYear || ym.month !== viewMonth) {
        setViewYear(ym.year);
        setViewMonth(ym.month);
      }
    },
    [today, viewYear, viewMonth],
  );

  const availableCount = useMemo(
    () => overview?.slots.filter((s) => s.status === "available").length ?? 0,
    [overview],
  );

  const handleBack = useCallback(() => {
    if (navigation.canGoBack()) {
      navigation.goBack();
    } else {
      router.replace("/(tabs)/");
    }
  }, [navigation, router]);

  const handleRefresh = useCallback(() => {
    setRefreshing(true);
    setCalendarLoading(true);
    void Promise.all([
      loadCalendar(viewYear, viewMonth),
      loadSlots(date),
    ]).finally(() => setRefreshing(false));
  }, [viewYear, viewMonth, date, loadCalendar, loadSlots]);

  const confirmBooking = async () => {
    if (!pendingSlot || !overview) return;
    const slot = pendingSlot;
    setSubmitting(true);
    const previous = overview;
    setOverview((prev) =>
      prev
        ? {
            ...prev,
            slots: prev.slots.map((s) =>
              s.slot_id === slot.slot_id
                ? { ...s, status: "booked" as const, is_mine: true }
                : s,
            ),
          }
        : prev,
    );
    setPendingSlot(null);
    try {
      const booking = await bookingService.create(date, slot.slot_id);
      setToast({ kind: "success", text: "Slot reserved" });
      presentInstantConfirmation(booking).catch(() => undefined);
      scheduleBookingReminders(booking).catch(() => undefined);
      bumpRefresh();
      void Promise.all([loadSlots(date), loadCalendar(viewYear, viewMonth)]);
    } catch (e) {
      setOverview(previous);
      setToast({ kind: "error", text: getFriendlyErrorMessage(e) });
    } finally {
      setSubmitting(false);
    }
  };

  const joinWaitlist = useCallback(async (slot: SlotView) => {
    if (joiningSlotId) return;
    setJoiningSlotId(slot.slot_id);
    const previous = overviewRef.current;
    setOverview((prev) =>
      prev
        ? {
            ...prev,
            slots: prev.slots.map((s) =>
              s.slot_id === slot.slot_id
                ? { ...s, is_waitlisted: true, waitlist_position: s.waitlist_position ?? 1 }
                : s,
            ),
          }
        : prev,
    );
    try {
      const result = await waitlistService.join(date, slot.slot_id);
      setOverview((prev) =>
        prev
          ? {
              ...prev,
              slots: prev.slots.map((s) =>
                s.slot_id === slot.slot_id
                  ? {
                      ...s,
                      is_waitlisted: true,
                      waitlist_position: result.position,
                      waitlist_id: result.waitlist_id,
                    }
                  : s,
              ),
            }
          : prev,
      );
      presentWaitlistJoined(slot.slot_label, date).catch(() => undefined);
      setToast({ kind: "success", text: `You're #${result.position} in the queue` });
      bumpRefresh();
    } catch (e) {
      setOverview(previous);
      setToast({ kind: "error", text: getFriendlyErrorMessage(e) });
    } finally {
      setJoiningSlotId(null);
    }
  }, [joiningSlotId, date, bumpRefresh]);

  const handleBookPress = useCallback((slotId: SlotId) => {
    if (!canBook) {
      setToast({ kind: "error", text: "You need booking access to reserve or cancel slots." });
      router.push("/request-access");
      return;
    }
    const slot = overviewRef.current?.slots.find((s) => s.slot_id === slotId);
    if (slot) setPendingSlot(slot);
  }, [canBook, router]);

  const handleJoinWaitlistPress = useCallback((slotId: SlotId) => {
    if (!canBook) {
      setToast({ kind: "error", text: "You need booking access to reserve or cancel slots." });
      router.push("/request-access");
      return;
    }
    const slot = overviewRef.current?.slots.find((s) => s.slot_id === slotId);
    if (slot) void joinWaitlist(slot);
  }, [canBook, joinWaitlist, router]);

  const bottomPad = insets.bottom + TAB_BAR_CLEARANCE;

  return (
    <SafeAreaView style={styles.container} edges={["top"]} testID="book-screen">
      <Toast message={toast} onHide={() => setToast(null)} />

      <View style={styles.navBar}>
        <Pressable
          onPress={handleBack}
          style={({ pressed }) => [styles.navBtn, pressed && styles.pressed]}
          hitSlop={8}
          accessibilityRole="button"
          accessibilityLabel="Go back"
          testID="book-back"
        >
          <Ionicons name="chevron-back" size={26} color={colors.text_primary} />
        </Pressable>

        <View style={styles.navCenter}>
          <Text style={styles.navTitle}>Book Turf</Text>
          {showUpdatedHint ? (
            <Text style={styles.updatedHint} testID="book-updated-hint">Updated just now</Text>
          ) : null}
        </View>

        <Pressable
          onPress={handleRefresh}
          disabled={refreshing}
          style={({ pressed }) => [styles.navBtn, pressed && styles.pressed, refreshing && styles.navBtnDisabled]}
          hitSlop={8}
          accessibilityRole="button"
          accessibilityLabel="Refresh"
          testID="book-refresh"
        >
          {refreshing ? (
            <ActivityIndicator size="small" color={colors.primary} />
          ) : (
            <Ionicons name="refresh-outline" size={22} color={colors.text_primary} />
          )}
        </Pressable>
      </View>

      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={[styles.scrollContent, { paddingBottom: bottomPad }]}
        nestedScrollEnabled
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={handleRefresh}
            tintColor={colors.primary}
          />
        }
      >
        <Text style={styles.dateHeading} testID="book-date-heading">
          {prettyDateLong(date)}
        </Text>
        {!canBook ? <BookingAccessBanner compact /> : null}
        {!loading && overview ? (
          <Text style={styles.availabilitySummary} testID="book-availability-summary">
            {availabilityLabel(availableCount, date, today)}
          </Text>
        ) : null}

        <BookingCalendar
          selectedDate={date}
          days={calendarDays}
          loading={calendarLoading}
          onSelectDate={selectDate}
        />

        <Text style={styles.slotsSectionTitle}>Choose a time</Text>

        {slowLoading && loading ? (
          <Text style={styles.slowHint}>Still loading...</Text>
        ) : null}

        {loadError && !loading && !overview ? (
          <ErrorState
            message={loadError}
            onRetry={() => {
              setLoading(true);
              setLoadError(null);
              loadSlots(date);
            }}
            testID="book-load-error"
          />
        ) : loading && !overview ? (
          <SkeletonSlotCards count={3} />
        ) : (
          overview?.slots.map((s) => (
            <SlotCard
              key={s.slot_id}
              slot={s}
              joining={joiningSlotId === s.slot_id}
              canBook={canBook}
              onBook={handleBookPress}
              onJoinWaitlist={handleJoinWaitlistPress}
            />
          ))
        )}
      </ScrollView>

      <Modal
        visible={!!pendingSlot}
        transparent
        animationType="fade"
        onRequestClose={() => !submitting && setPendingSlot(null)}
      >
        <View style={styles.modalBackdrop} testID="confirm-modal">
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>Confirm booking</Text>
            <Text style={styles.modalDate}>{prettyDateLong(date)}</Text>
            <Text style={styles.modalTime}>
              {pendingSlot ? prettyRange(pendingSlot.start_time, pendingSlot.end_time) : ""}
            </Text>
            <View style={{ height: spacing.lg }} />
            <Button
              label="Confirm"
              loadingLabel="Booking..."
              onPress={confirmBooking}
              loading={submitting}
              testID="confirm-modal-confirm"
            />
            <View style={{ height: spacing.sm }} />
            <Button
              label="Cancel"
              variant="ghost"
              onPress={() => setPendingSlot(null)}
              disabled={submitting}
              testID="confirm-modal-cancel"
            />
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

interface SlotCardProps {
  slot: SlotView;
  joining?: boolean;
  canBook: boolean;
  onBook: (slotId: SlotId) => void;
  onJoinWaitlist: (slotId: SlotId) => void;
}

const SlotCard = memo(function SlotCard({ slot, joining, canBook, onBook, onJoinWaitlist }: SlotCardProps) {
  const visual = slotVisual(slot);
  const isBookedByOther = slot.status === "booked" && !slot.is_mine && !slot.is_waitlisted;
  const canJoinWaitlist = isBookedByOther && slot.status !== "completed";

  const actionLabel =
    visual === "available"
      ? "Book"
      : visual === "mine"
        ? "Booked"
        : slot.is_waitlisted
          ? "Waitlisted"
          : "Unavailable";

  const actionDisabled = visual !== "available" || !canBook;

  return (
    <View
      style={[
        styles.slot,
        visual === "available" && styles.slotAvailable,
        visual === "mine" && styles.slotMine,
        visual === "unavailable" && styles.slotUnavailable,
      ]}
      testID={`slot-card-${slot.slot_id}`}
    >
      <View style={styles.slotMain}>
        <View style={styles.slotContent}>
          <Text style={[styles.slotTime, visual === "unavailable" && styles.textMuted]}>
            {prettyRange(slot.start_time, slot.end_time)}
          </Text>
          {visual === "mine" ? (
            <View style={styles.mineRow}>
              <Ionicons name="checkmark-circle" size={16} color={colors.primary} />
              <Text style={styles.mineLabel}>Your booking</Text>
            </View>
          ) : slot.is_waitlisted && slot.waitlist_position ? (
            <Text style={styles.metaText} testID={`slot-queue-${slot.slot_id}`}>
              Queue position #{slot.waitlist_position}
            </Text>
          ) : isBookedByOther ? (
            <Text style={styles.metaText} testID={`slot-booked-by-${slot.slot_id}`}>
              {formatBookerBookedText(slot.booker_name, slot.booker_student_id)}
            </Text>
          ) : slot.status === "completed" ? (
            <Text style={styles.metaText}>Session ended</Text>
          ) : null}
        </View>

        <Button
          label={actionLabel}
          variant={visual === "available" ? "primary" : "secondary"}
          onPress={() => onBook(slot.slot_id)}
          disabled={actionDisabled}
          fullWidth={false}
          style={styles.slotAction}
          testID={
            visual === "available"
              ? `slot-book-${slot.slot_id}`
              : `slot-unavailable-${slot.slot_id}`
          }
        />
      </View>

      {canJoinWaitlist && canBook ? (
        <Button
          label="Join waitlist"
          loadingLabel="Joining..."
          variant="secondary"
          onPress={() => onJoinWaitlist(slot.slot_id)}
          loading={joining}
          disabled={joining}
          testID={`slot-waitlist-${slot.slot_id}`}
        />
      ) : null}
    </View>
  );
});

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  navBar: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  navBtn: {
    width: 44,
    height: 44,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: CARD_RADIUS,
  },
  navBtnDisabled: { opacity: 0.5 },
  navCenter: { flex: 1, alignItems: "center" },
  navTitle: { ...typography.bodyBold, fontSize: 17, color: colors.text_primary },
  updatedHint: {
    ...typography.caption,
    color: colors.text_tertiary,
    marginTop: 2,
  },
  scrollView: { flex: 1 },
  scrollContent: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    gap: spacing.md,
  },
  dateHeading: {
    ...typography.h2,
    fontSize: 24,
    letterSpacing: -0.4,
    color: colors.text_primary,
  },
  availabilitySummary: {
    ...typography.body,
    color: colors.text_secondary,
    marginTop: -spacing.xs,
  },
  slotsSectionTitle: {
    ...typography.label,
    color: colors.text_tertiary,
    fontSize: 11,
  },
  slowHint: {
    ...typography.caption,
    color: colors.text_secondary,
    textAlign: "center",
  },

  slot: {
    borderRadius: CARD_RADIUS,
    borderWidth: StyleSheet.hairlineWidth,
    padding: spacing.md,
    gap: spacing.sm,
    shadowColor: "#0F172A",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 8,
    elevation: 1,
  },
  slotAvailable: {
    backgroundColor: "#ECFDF5",
    borderColor: "#BBF7D0",
  },
  slotMine: {
    backgroundColor: "#EFF6FF",
    borderColor: "#93C5FD",
  },
  slotUnavailable: {
    backgroundColor: "#F8FAFC",
    borderColor: colors.border,
  },
  slotMain: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: spacing.md,
  },
  slotContent: { flex: 1, gap: 4 },
  slotTime: {
    ...typography.bodyBold,
    fontSize: 17,
    color: colors.text_primary,
  },
  textMuted: { color: colors.text_tertiary },
  mineRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  mineLabel: { ...typography.caption, color: colors.primary, fontWeight: "600" },
  metaText: { ...typography.caption, color: colors.text_secondary },
  slotAction: {
    minWidth: 96,
    minHeight: 44,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: CARD_RADIUS,
  },
  pressed: { opacity: 0.85 },

  modalBackdrop: {
    flex: 1,
    backgroundColor: "rgba(15,23,42,0.45)",
    justifyContent: "center",
    padding: spacing.lg,
  },
  modalCard: {
    backgroundColor: colors.background,
    borderRadius: CARD_RADIUS,
    padding: spacing.lg,
  },
  modalTitle: { ...typography.h2, fontSize: 22, color: colors.text_primary },
  modalDate: { ...typography.bodyBold, color: colors.text_primary, marginTop: spacing.sm },
  modalTime: { ...typography.body, color: colors.text_secondary, marginTop: 4 },
});
