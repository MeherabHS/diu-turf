/** Canonical UUID hex comparison for WS payloads and auth IDs. */
export function uuidHex(value: unknown): string {
  if (value == null) return "";
  const raw = String(value).replace(/-/g, "").toLowerCase();
  return raw.length === 32 ? raw : String(value).toLowerCase();
}

export function uuidSame(a: unknown, b: unknown): boolean {
  return uuidHex(a) === uuidHex(b);
}
