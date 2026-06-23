/** Phase 3 type additions. */
export type SlotId = string;
export type SlotStatus = "available" | "booked" | "completed" | "maintenance";
export type BookingStatus = "booked" | "completed" | "cancelled";
export type ActivityAction = "BOOKED" | "CANCELLED" | "COMPLETED" | "EXPIRED";

export interface Booking {
  booking_id: string;
  user_id: string;
  student_name: string;
  student_id: string;
  email: string;
  booking_date: string;
  slot_id: SlotId;
  slot_label: string;
  start_time: string;
  end_time: string;
  status: BookingStatus;
  created_at: string;
  updated_at: string;
  day_of_week: number;
  hour: number;
  booking_lead_time: number;
  department?: string | null;
  batch?: string | null;
}

export interface SlotView {
  slot_id: SlotId;
  slot_label: string;
  start_time: string;
  end_time: string;
  booking_date: string;
  status: SlotStatus;
  booking: Booking | null;
  is_mine: boolean;
  is_waitlisted?: boolean;
  waitlist_position?: number | null;
  waitlist_id?: string | null;
  booker_name?: string | null;
  booker_student_id?: string | null;
}

export interface WaitlistEntry {
  waitlist_id: string;
  booking_date: string;
  slot_id: SlotId;
  slot_label: string;
  start_time: string;
  end_time: string;
  position: number;
  status: string;
  created_at: string;
}

export interface DateOverview {
  booking_date: string;
  slots: SlotView[];
}

export interface OccupancyResponse {
  booking_date: string;
  total_slots: number;
  filled_slots: number;
  percentage: number;
}

export interface CalendarDay {
  date: string;
  total: number;
  mine: number;
  fully_booked: boolean;
}

export interface CalendarResponse {
  year: number;
  month: number;
  days: CalendarDay[];
}

export interface WeeklyUsage {
  week_start: string;
  bookings_made: number;
  bookings_limit: number;
  cancellations_made: number;
  cancellations_limit: number;
}

export interface ActivityItem {
  activity_id: string;
  action: ActivityAction | string;
  event_type?: string;
  user_id: string;
  student_name: string;
  student_id?: string | null;
  message?: string | null;
  booking_id?: string | null;
  booking_date?: string | null;
  slot_id?: SlotId | null;
  slot_label?: string | null;
  created_at: string;
}

export interface NotificationItem {
  notification_id: string;
  user_id: string;
  title: string;
  message: string;
  kind: string;
  read: boolean;
  created_at: string;
  booking_id?: string | null;
}
