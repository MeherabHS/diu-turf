/** Display helpers for user identity in headers and labels. */
import type { User } from "@/src/types";

export function displayName(user: Pick<User, "name" | "student_id"> | null | undefined): string {
  const name = user?.name?.trim();
  if (name) return name;
  return user?.student_id?.trim() || "Student";
}

export function profileSubtext(user: Pick<User, "student_id" | "department" | "batch"> | null | undefined): string {
  const parts: string[] = [];
  const studentId = user?.student_id?.trim();
  if (studentId) parts.push(studentId);
  const deptBatch = [user?.department?.trim(), user?.batch?.trim()].filter(Boolean).join(" ");
  if (deptBatch) parts.push(deptBatch);
  return parts.join(" · ");
}

export function formatBookerLabel(name?: string | null, studentId?: string | null): string {
  const id = studentId?.trim();
  const n = name?.trim();
  if (n && id && n !== id) return `${n} (${id})`;
  if (n) return n;
  if (id) return id;
  return "Someone";
}

export function formatBookerBookedText(name?: string | null, studentId?: string | null): string {
  return `${formatBookerLabel(name, studentId)} booked this slot`;
}
