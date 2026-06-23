/** Shared refresh signal for booking-related screens (WS + local cancel/create). */
import { create } from "zustand";

interface BookingsRefreshState {
  nonce: number;
  bump: () => void;
}

export const useBookingsRefreshStore = create<BookingsRefreshState>((set) => ({
  nonce: 0,
  bump: () => set((s) => ({ nonce: s.nonce + 1 })),
}));
