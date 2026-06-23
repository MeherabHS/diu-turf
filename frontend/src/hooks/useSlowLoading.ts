/** True after `delayMs` of continuous loading — for "Still loading..." hints. */
import { useEffect, useState } from "react";

export function useSlowLoading(loading: boolean, delayMs = 3000): boolean {
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    if (!loading) {
      setSlow(false);
      return;
    }
    const id = setTimeout(() => setSlow(true), delayMs);
    return () => clearTimeout(id);
  }, [loading, delayMs]);

  return slow;
}
