/** Booking API client. */
import { api } from "./api";
import type { Booking, DateOverview, SlotId } from "@/src/types/booking";

export const bookingService = {
  forDate: (date: string) => api.get<DateOverview>(`/api/bookings/date/${date}`),
  mine: () => api.get<Booking[]>("/api/bookings/me"),
  create: (booking_date: string, slot_id: SlotId) =>
    api.post<Booking>("/api/bookings", { booking_date, slot_id }),
  cancel: (booking_id: string) => api.del<{ ok: boolean }>(`/api/bookings/${booking_id}`),
};
