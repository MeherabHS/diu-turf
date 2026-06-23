/** Horizontal date strip — swipe to browse, tap to select. No nested vertical scroll. */
import React, { memo, useEffect, useMemo, useRef } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { format, parseISO } from "date-fns";

import { colors, spacing, typography } from "@/src/theme";
import type { CalendarDay } from "@/src/types/booking";
import { shiftDate, todayDhakaDateString } from "@/src/utils/datetime";

const CARD_RADIUS = 16;
const DATE_CHIP_WIDTH = 64;
const DATE_CHIP_GAP = 8;
const HORIZON_DAYS = 90;

type DayTone = "available" | "mine" | "full";

function toneForDay(dateStr: string, info?: CalendarDay): DayTone {
  if (info && info.mine > 0) return "mine";
  if (info?.fully_booked) return "full";
  return "available";
}

interface Props {
  selectedDate: string;
  days: CalendarDay[];
  loading?: boolean;
  onSelectDate: (date: string) => void;
}

export const BookingCalendar = memo(function BookingCalendar({
  selectedDate,
  days,
  loading,
  onSelectDate,
}: Props) {
  const today = todayDhakaDateString();
  const scrollRef = useRef<ScrollView>(null);
  const dayMap = useMemo(() => new Map(days.map((d) => [d.date, d])), [days]);

  const dates = useMemo(() => {
    const list: string[] = [];
    for (let i = 0; i < HORIZON_DAYS; i++) {
      list.push(shiftDate(today, i));
    }
    return list;
  }, [today]);

  const monthLabel = useMemo(() => {
    const d = parseISO(selectedDate);
    return format(d, "MMMM yyyy");
  }, [selectedDate]);

  useEffect(() => {
    const idx = dates.indexOf(selectedDate);
    if (idx < 0 || !scrollRef.current) return;
    const x = Math.max(0, idx * (DATE_CHIP_WIDTH + DATE_CHIP_GAP) - spacing.lg);
    scrollRef.current.scrollTo({ x, animated: true });
  }, [selectedDate, dates]);

  return (
    <View style={styles.wrap} testID="booking-calendar">
      <Text style={styles.monthTitle} testID="calendar-month-label">
        {monthLabel}
      </Text>

      {loading ? (
        <ActivityIndicator color={colors.primary} style={styles.loader} />
      ) : (
        <ScrollView
          ref={scrollRef}
          horizontal
          showsHorizontalScrollIndicator={false}
          nestedScrollEnabled
          directionalLockEnabled
          decelerationRate="fast"
          contentContainerStyle={styles.stripContent}
          testID="calendar-date-strip"
        >
          {dates.map((dateStr) => {
            const tone = toneForDay(dateStr, dayMap.get(dateStr));
            const selected = dateStr === selectedDate;
            const d = parseISO(dateStr);
            const weekday = format(d, "EEE");
            const dayNum = format(d, "d");
            const isToday = dateStr === today;

            return (
              <Pressable
                key={dateStr}
                onPress={() => onSelectDate(dateStr)}
                style={({ pressed }) => [
                  styles.chip,
                  tone === "available" && styles.chipAvailable,
                  tone === "mine" && styles.chipMine,
                  tone === "full" && styles.chipFull,
                  selected && styles.chipSelected,
                  pressed && styles.pressed,
                ]}
                testID={`calendar-day-${dateStr}`}
              >
                <Text style={[styles.chipWeekday, selected && styles.chipTextSelected]}>
                  {isToday ? "Today" : weekday}
                </Text>
                <Text style={[styles.chipDay, selected && styles.chipTextSelected]}>{dayNum}</Text>
              </Pressable>
            );
          })}
        </ScrollView>
      )}
    </View>
  );
});

const styles = StyleSheet.create({
  wrap: {
    backgroundColor: colors.surface,
    borderRadius: CARD_RADIUS,
    paddingVertical: spacing.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    shadowColor: "#0F172A",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 8,
    elevation: 1,
    overflow: "visible",
  },
  monthTitle: {
    ...typography.bodyBold,
    fontSize: 15,
    color: colors.text_secondary,
    paddingHorizontal: spacing.md,
    marginBottom: spacing.sm,
  },
  loader: { marginVertical: spacing.md },
  stripContent: {
    paddingHorizontal: spacing.md,
    paddingBottom: 2,
    gap: DATE_CHIP_GAP,
  },
  chip: {
    width: DATE_CHIP_WIDTH,
    paddingVertical: spacing.sm,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: "transparent",
  },
  chipAvailable: { backgroundColor: "#ECFDF5" },
  chipMine: { backgroundColor: "#DBEAFE" },
  chipFull: { backgroundColor: colors.surface_secondary },
  chipSelected: {
    borderColor: colors.text_primary,
    borderWidth: 1.5,
  },
  chipWeekday: {
    ...typography.caption,
    fontSize: 11,
    color: colors.text_tertiary,
    fontWeight: "600",
    marginBottom: 2,
  },
  chipDay: {
    ...typography.bodyBold,
    fontSize: 18,
    color: colors.text_primary,
  },
  chipTextSelected: { color: colors.text_primary },
  pressed: { opacity: 0.85 },
});
