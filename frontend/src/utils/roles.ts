/** Role helpers — booking access is assigned server-side. */
import type { Role } from "@/src/types";

const BOOKING_ROLES: ReadonlySet<Role | string> = new Set(["booker", "admin", "super_admin"]);
const VIEW_ONLY_ROLES: ReadonlySet<Role | string> = new Set(["viewer", "student"]);

export function isAdminRole(role: Role | string | null | undefined): boolean {
  return role === "admin" || role === "super_admin";
}

export function canBookSlots(role: Role | string | null | undefined): boolean {
  return role != null && BOOKING_ROLES.has(role);
}

export function isViewOnlyStudent(role: Role | string | null | undefined): boolean {
  if (role == null) return true;
  if (canBookSlots(role) || isAdminRole(role)) return false;
  return VIEW_ONLY_ROLES.has(role) || true;
}

export function roleDisplayLabel(role: Role | string | null | undefined): string {
  switch (role) {
    case "viewer":
    case "student":
      return "View only";
    case "booker":
      return "Can book";
    case "admin":
    case "super_admin":
      return "Admin";
    default:
      return "View only";
  }
}
