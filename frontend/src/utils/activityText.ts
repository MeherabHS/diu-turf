/** Activity feed display helpers. */
import type { ActivityItem } from "@/src/types/booking";

export function getActivityDisplayText(item: ActivityItem): string {
  const message = item.message?.trim();
  if (message && !message.startsWith("[DEV]")) return message;

  if (item.event_type?.startsWith("auth.")) return "";

  const name = item.student_name?.trim();
  const slot = item.slot_label?.trim();
  const date = item.booking_date?.trim();

  if (item.action === "BOOKED" && (name || slot)) {
    const who = name || "You";
    const where = slot ? ` ${slot}` : "";
    const when = date ? ` on ${date}` : "";
    return `${who} booked${where}${when}`.trim();
  }
  if (item.action === "CANCELLED" && (name || slot)) {
    const who = name || "You";
    const where = slot ? ` ${slot}` : "";
    const when = date ? ` on ${date}` : "";
    return `${who} cancelled${where}${when}`.trim();
  }

  return message || "";
}

export function isMeaningfulActivity(item: ActivityItem): boolean {
  const eventType = item.event_type ?? "";
  if (eventType.startsWith("auth.")) return false;
  if (eventType.startsWith("admin.")) return false;
  return getActivityDisplayText(item).length > 0;
}
