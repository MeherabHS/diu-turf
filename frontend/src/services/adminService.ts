/** Admin API client — student management. */
import { api } from "./api";

export type StudentStatus = "active" | "suspended" | "inactive";
export type SuspendDuration = "1d" | "7d" | "30d" | "permanent";

export interface StudentListItem {
  user_id: string;
  student_id: string | null;
  name: string;
  email: string;
  role?: string;
  booking_count: number;
  status: StudentStatus;
  suspended: boolean;
}

export interface StudentStats {
  total: number;
  active: number;
  suspended: number;
}

export interface StudentsPage {
  items: StudentListItem[];
  page: number;
  page_size: number;
  total: number;
  stats: StudentStats;
}

export interface StudentProfile {
  user_id: string;
  name: string;
  email: string;
  student_id: string | null;
  role?: string;
  department: string | null;
  batch: string | null;
  booking_count?: number;
  status: StudentStatus;
  suspended: boolean;
  suspension_until: string | null;
  suspension_reason: string | null;
  last_login: string | null;
  created_at: string | null;
}

export interface StudentBookingRow {
  booking_id: string;
  booking_date: string;
  slot_id: string;
  slot_label: string;
  time_range: string;
  status: string;
  created_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
}

export interface StudentAttendanceRow {
  status: string;
  marked_at: string | null;
  note: string | null;
  booking_date: string;
  slot_id: string;
  slot_label: string;
  time_range: string;
}

export interface StudentDetail {
  profile: StudentProfile;
  bookings: StudentBookingRow[];
  cancellations: StudentBookingRow[];
  attendance: StudentAttendanceRow[];
}

export interface AdminBookingRow extends StudentBookingRow {
  student_name: string;
  student_email: string;
  student_id: string | null;
}

export interface AdminBookingsPage {
  items: AdminBookingRow[];
  page: number;
  page_size: number;
  total: number;
}

export interface AdminSlotRow {
  id: string;
  turf_id: string;
  slot_key: string;
  start_time: string;
  end_time: string;
  is_active: boolean;
}

export interface SlotUpsertPayload {
  slot_key: string;
  start_time: string;
  end_time: string;
  is_active?: boolean;
}

function qs(params: Record<string, string | number | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export const adminService = {
  listStudents: (opts: { q?: string; page?: number; page_size?: number } = {}) =>
    api.get<StudentsPage>(
      `/api/admin/students${qs({
        q: opts.q,
        page: opts.page ?? 1,
        page_size: opts.page_size ?? 20,
      })}`,
    ),

  getStudent: (userId: string) => api.get<StudentDetail>(`/api/admin/students/${userId}`),

  suspend: (userId: string, body: { duration: SuspendDuration; reason: string }) =>
    api.post<{ ok: boolean; until: string }>(`/api/admin/students/${userId}/suspend`, body),

  unsuspend: (userId: string) =>
    api.post<{ ok: boolean }>(`/api/admin/students/${userId}/unsuspend`),

  activate: (userId: string) =>
    api.post<{ ok: boolean }>(`/api/admin/students/${userId}/activate`),

  listBookings: (opts: { page?: number; page_size?: number } = {}) =>
    api.get<AdminBookingsPage>(
      `/api/admin/bookings${qs({
        page: opts.page ?? 1,
        page_size: opts.page_size ?? 20,
      })}`,
    ),

  listSlots: () => api.get<AdminSlotRow[]>("/api/admin/slots"),

  createSlot: (body: Omit<SlotUpsertPayload, "is_active">) =>
    api.post<AdminSlotRow>("/api/admin/slots", body),

  updateSlot: (slotId: string, body: SlotUpsertPayload) =>
    api.put<AdminSlotRow>(`/api/admin/slots/${slotId}`, {
      ...body,
      is_active: body.is_active ?? true,
    }),

  disableSlot: (slotId: string) =>
    api.patch<AdminSlotRow>(`/api/admin/slots/${slotId}/disable`),

  enableSlot: (slotId: string) =>
    api.patch<AdminSlotRow>(`/api/admin/slots/${slotId}/enable`),

  listAccessRequests: (status?: "pending" | "approved" | "rejected") =>
    api.get<AccessRequestRow[]>(
      `/api/admin/access-requests${status ? `?status=${status}` : ""}`,
    ),

  approveAccessRequest: (requestId: string) =>
    api.post<AccessRequestRow>(`/api/admin/access-requests/${requestId}/approve`),

  rejectAccessRequest: (requestId: string) =>
    api.post<AccessRequestRow>(`/api/admin/access-requests/${requestId}/reject`),
};

export interface AccessRequestRow {
  id: string;
  user_id: string;
  name: string;
  email: string;
  student_id: string | null;
  reason: string | null;
  status: "pending" | "approved" | "rejected";
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}
