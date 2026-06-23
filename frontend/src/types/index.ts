/** Type definitions — Phase 4 update.
 *
 * Changes:
 *  - AuthResponse.token → AuthResponse.access_token (matches backend).
 *  - User: added google_sub field.
 *  - Role: added super_admin.
 *  - SlotKey: kept as-is (A/B/C already correct since Phase 1).
 *  - Added LoginPayload and RegisterPayload stubs for Phase 5+ email auth.
 */

export type Role = "viewer" | "booker" | "student" | "admin" | "super_admin";
export type SlotKey = string;
export type SlotStatus = "available" | "booked" | "completed" | "maintenance";

export interface User {
  user_id: string;
  email: string;
  name: string;
  picture?: string | null;
  google_sub?: string | null;
  role: Role;
  student_id?: string | null;
  department?: string | null;
  batch?: string | null;
  room_number?: string | null;
  hostel_name?: string | null;
  phone?: string | null;
  profile_completed: boolean;
  created_at: string;
  last_login?: string | null;
  updated_at: string;
}

/** Returned by POST /api/auth/google. */
export interface AuthResponse {
  access_token: string;   // renamed from 'token' in Phase 4
  user: User;
}

/** Returned by GET /api/auth/me. */
export interface AuthMeResponse {
  user: User;
}

export interface ProfilePayload {
  name: string;
  student_id: string;
  department: string;
  batch: string;
  room_number?: string | null;
  hostel_name?: string | null;
  phone?: string | null;
}

export interface Slot {
  slot_id: string;
  date: string;
  slot_key: SlotKey;
  label: string;
  start_time: string;
  end_time: string;
  status: SlotStatus;
  booked_by?: string | null;
  booked_by_name?: string | null;
  booked_by_student_id?: string | null;
}
