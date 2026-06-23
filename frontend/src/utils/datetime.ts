/** Booking helpers — date formatting + time labels. */
import {
  addDays,
  addMonths,
  format,
  isToday,
  isYesterday,
  parseISO,
  startOfMonth,
  endOfMonth,
  getDay,
} from "date-fns";

/** YYYY-MM-DD in turf-local timezone (Asia/Dhaka, UTC+6). Backend interprets the same. */
export function todayDhakaDateString(): string {
  // Compute "now in Dhaka" by adding +6h to UTC and grabbing the date.
  const nowUtc = new Date();
  const dhakaMs = nowUtc.getTime() + 6 * 60 * 60 * 1000;
  const d = new Date(dhakaMs);
  return d.toISOString().slice(0, 10);
}

export function shiftDate(yyyyMmDd: string, days: number): string {
  return format(addDays(parseISO(yyyyMmDd), days), "yyyy-MM-dd");
}

export function prettyDate(yyyyMmDd: string): string {
  return format(parseISO(yyyyMmDd), "EEE, dd MMM yyyy");
}

export function prettyDateLong(yyyyMmDd: string): string {
  return format(parseISO(yyyyMmDd), "EEEE, dd MMMM yyyy");
}

/** "16:00" → "4:00 PM" */
export function pretty12h(hhmm: string): string {
  const [hStr, mStr] = hhmm.split(":");
  const h = Number(hStr);
  const m = Number(mStr);
  const period = h >= 12 ? "PM" : "AM";
  const h12 = ((h + 11) % 12) + 1;
  return `${h12}:${m.toString().padStart(2, "0")} ${period}`;
}

export function prettyRange(start: string, end: string): string {
  return `${pretty12h(start)} – ${pretty12h(end)}`;
}

export function formatShortDate(yyyyMmDd: string): string {
  return format(parseISO(yyyyMmDd), "dd MMM yyyy");
}

/** Time-of-day greeting for the home screen header. */
export function timeOfDayGreeting(date = new Date()): string {
  const hour = date.getHours();
  if (hour < 12) return "Good Morning";
  if (hour < 17) return "Good Afternoon";
  return "Good Evening";
}

/** Friendly timestamp for activity previews — e.g. "Today, 4:15 PM". */
export function formatActivityWhen(iso: string): string {
  const d = parseISO(iso);
  const time = format(d, "h:mm a");
  if (isToday(d)) return `Today, ${time}`;
  if (isYesterday(d)) return `Yesterday, ${time}`;
  return format(d, "EEE, MMM d · h:mm a");
}

export function monthLabel(year: number, month: number): string {
  return format(new Date(year, month - 1, 1), "MMMM yyyy");
}

export function parseYearMonth(dateStr: string): { year: number; month: number } {
  const [y, m] = dateStr.split("-").map(Number);
  return { year: y, month: m };
}

/** Build a Monday-start calendar grid for a month (includes adjacent-month padding). */
export function monthGrid(year: number, month: number): { date: string; inMonth: boolean }[] {
  const start = startOfMonth(new Date(year, month - 1, 1));
  const end = endOfMonth(start);
  const leading = (getDay(start) + 6) % 7;
  const cells: { date: string; inMonth: boolean }[] = [];

  for (let i = leading; i > 0; i--) {
    cells.push({ date: format(addDays(start, -i), "yyyy-MM-dd"), inMonth: false });
  }
  for (let d = start; d <= end; d = addDays(d, 1)) {
    cells.push({ date: format(d, "yyyy-MM-dd"), inMonth: true });
  }
  while (cells.length % 7 !== 0) {
    const tail = parseISO(cells[cells.length - 1].date);
    cells.push({ date: format(addDays(tail, 1), "yyyy-MM-dd"), inMonth: false });
  }
  return cells;
}

export function shiftMonth(year: number, month: number, delta: number): { year: number; month: number } {
  const d = addMonths(new Date(year, month - 1, 1), delta);
  return { year: d.getFullYear(), month: d.getMonth() + 1 };
}
