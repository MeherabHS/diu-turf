/** Refetch on screen focus or WS booking/waitlist events — not on timers. */
import { useFocusEffect } from "expo-router";
import { useCallback, useEffect } from "react";

import { useBookingsRefreshNonce } from "@/src/hooks/useBookingsLive";

export function useLiveScreenRefresh(load: () => void | Promise<void>): void {
  const nonce = useBookingsRefreshNonce();
  const run = useCallback(() => {
    void load();
  }, [load]);

  useFocusEffect(
    useCallback(() => {
      run();
    }, [run]),
  );

  useEffect(() => {
    if (nonce > 0) run();
  }, [nonce, run]);
}
