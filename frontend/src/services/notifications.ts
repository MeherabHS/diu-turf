/** Local-notification scheduler for booking reminders.
 *
 * Schedules 30/15/5-minute reminders for an active booking using
 * expo-notifications. Works in Expo Go and dev/prod builds.
 *
 * On platforms without notification support (e.g. web preview), the calls
 * silently no-op.
 */
import { Platform } from "react-native";
import * as Notifications from "expo-notifications";

import type { Booking } from "@/src/types/booking";
import { dhakaUtcMs } from "@/src/hooks/useTicker";
import { formatShortDate } from "@/src/utils/datetime";

const REMINDER_OFFSETS_MIN = [30, 15, 5];

let _configured = false;

async function ensureConfigured(): Promise<boolean> {
  if (Platform.OS === "web") return false;
  if (_configured) return true;
  try {
    Notifications.setNotificationHandler({
      handleNotification: async () => ({
        shouldShowBanner: true,
        shouldShowList: true,
        shouldPlaySound: true,
        shouldSetBadge: false,
      }),
    });
    const settings = await Notifications.getPermissionsAsync();
    let granted =
      settings.granted ||
      settings.ios?.status === Notifications.IosAuthorizationStatus.PROVISIONAL;
    if (!granted) {
      const req = await Notifications.requestPermissionsAsync();
      granted =
        req.granted ||
        req.ios?.status === Notifications.IosAuthorizationStatus.PROVISIONAL;
    }
    _configured = true;
    return granted;
  } catch {
    return false;
  }
}

function reminderId(bookingId: string, offsetMin: number): string {
  return `bk-${bookingId}-${offsetMin}`;
}

export async function scheduleBookingReminders(b: Booking): Promise<void> {
  const ok = await ensureConfigured();
  if (!ok) return;
  const startMs = dhakaUtcMs(b.booking_date, b.start_time);
  for (const offset of REMINDER_OFFSETS_MIN) {
    const triggerMs = startMs - offset * 60_000;
    if (triggerMs - Date.now() < 5_000) continue; // skip past-due
    try {
      await Notifications.scheduleNotificationAsync({
        identifier: reminderId(b.booking_id, offset),
        content: {
          title: "Reminder",
          body: `Your turf slot starts in ${offset} minutes.\nTime: ${b.start_time}–${b.end_time}`,
        },
        trigger: {
          type: Notifications.SchedulableTriggerInputTypes.DATE,
          date: new Date(triggerMs),
        },
      });
    } catch {
      // ignore — best-effort
    }
  }
}

export async function cancelBookingReminders(bookingId: string): Promise<void> {
  if (Platform.OS === "web") return;
  for (const offset of REMINDER_OFFSETS_MIN) {
    try {
      await Notifications.cancelScheduledNotificationAsync(reminderId(bookingId, offset));
    } catch {
      // ignore
    }
  }
}

type BookingNotice = Pick<Booking, "start_time" | "end_time" | "booking_date">;

async function presentInstantBookingNotice(title: string, b: BookingNotice): Promise<void> {
  const ok = await ensureConfigured();
  if (!ok) return;
  try {
    await Notifications.scheduleNotificationAsync({
      content: {
        title,
        body: `Slot: ${b.start_time}–${b.end_time} · ${b.booking_date}`,
      },
      trigger: null,
    });
  } catch {
    // ignore
  }
}

export async function presentInstantConfirmation(b: Booking): Promise<void> {
  await presentInstantBookingNotice("Booking Confirmed", b);
}

export async function presentInstantCancellation(b: BookingNotice): Promise<void> {
  await presentInstantBookingNotice("Booking Cancelled", b);
}

export async function presentWaitlistJoined(slotLabel: string, bookingDate: string): Promise<void> {
  const ok = await ensureConfigured();
  if (!ok) return;
  try {
    await Notifications.scheduleNotificationAsync({
      content: {
        title: "Waitlist Joined",
        body: `You joined the waitlist for ${slotLabel} on ${formatShortDate(bookingDate)}.`,
      },
      trigger: null,
    });
  } catch {
    // ignore
  }
}

export async function presentWaitlistPromotion(): Promise<void> {
  const ok = await ensureConfigured();
  if (!ok) return;
  try {
    await Notifications.scheduleNotificationAsync({
      content: {
        title: "Slot confirmed",
        body: "Your waitlisted turf slot is now confirmed.",
      },
      trigger: null,
    });
  } catch {
    // ignore
  }
}
