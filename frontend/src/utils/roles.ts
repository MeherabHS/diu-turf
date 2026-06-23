/** Role helpers — admin access is assigned server-side at login. */
import type { Role } from "@/src/types";

export function isAdminRole(role: Role | string | null | undefined): boolean {
  return role === "admin" || role === "super_admin";
}
