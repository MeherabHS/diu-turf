/** Re-render every `ms` ms — for countdowns. */
import { useEffect, useState } from "react";

export function useTicker(ms = 1000): number {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), ms);
    return () => clearInterval(id);
  }, [ms]);
  return tick;
}

/** Compute Asia/Dhaka UTC ms for a YYYY-MM-DD + "HH:MM". */
export function dhakaUtcMs(yyyyMmDd: string, hhmm: string): number {
  const [hh, mm] = hhmm.split(":").map(Number);
  return Date.UTC(
    Number(yyyyMmDd.slice(0, 4)),
    Number(yyyyMmDd.slice(5, 7)) - 1,
    Number(yyyyMmDd.slice(8, 10)),
    hh - 6,
    mm,
  );
}

/** Format `ms` as "01h 12m 03s" or "12m 03s" if < 1h. */
export function formatCountdown(ms: number): string {
  if (ms <= 0) return "00m 00s";
  const total = Math.floor(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => n.toString().padStart(2, "0");
  if (h > 0) return `${pad(h)}h ${pad(m)}m ${pad(s)}s`;
  return `${pad(m)}m ${pad(s)}s`;
}
