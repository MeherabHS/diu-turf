/** Waitlist API client. */
import { api } from "./api";
import type { SlotId, WaitlistEntry } from "@/src/types/booking";

export interface WaitlistJoinResponse {
  waitlist_id: string;
  position: number;
  status: string;
}

export const waitlistService = {
  join: (booking_date: string, slot_id: SlotId) =>
    api.post<WaitlistJoinResponse>("/api/waitlists", { booking_date, slot_id }),
  mine: () => api.get<WaitlistEntry[]>("/api/waitlists/me"),
  leave: (waitlist_id: string) => api.del<{ ok: boolean }>(`/api/waitlists/${waitlist_id}`),
};
