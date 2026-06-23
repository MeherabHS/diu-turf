/** Cached access-request state scoped to the signed-in user. */
import { useCallback, useEffect, useRef, useState } from "react";

import {
  accessRequestService,
  type AccessRequest,
} from "@/src/services/accessRequestService";
import { useAuthStore } from "@/src/store/useAuthStore";
import { getUserCache, setUserCache, USER_CACHE_SUFFIX } from "@/src/utils/userCache";

export function useAccessRequest() {
  const user = useAuthStore((s) => s.user);
  const refreshMe = useAuthStore((s) => s.refreshMe);
  const userId = user?.user_id ?? "";

  const [request, setRequest] = useState<AccessRequest | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const loadedFor = useRef<string | null>(null);

  const load = useCallback(async (opts?: { background?: boolean }) => {
    if (!userId) {
      setRequest(null);
      setLoading(false);
      return;
    }
    if (!opts?.background) setLoading(true);
    setError(null);
    try {
      const cached = await getUserCache<AccessRequest | null>(
        userId,
        USER_CACHE_SUFFIX.accessRequest,
        null,
      );
      if (cached) setRequest(cached);

      const fresh = await accessRequestService.mine();
      setRequest(fresh);
      await setUserCache(userId, USER_CACHE_SUFFIX.accessRequest, fresh as AccessRequest | null);

      if (fresh?.status === "approved") {
        await refreshMe();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to load request status");
    } finally {
      setLoading(false);
    }
  }, [userId, refreshMe]);

  useEffect(() => {
    if (loadedFor.current === userId) return;
    loadedFor.current = userId;
    setRequest(null);
    void load();
  }, [userId, load]);

  const submit = useCallback(
    async (reason?: string) => {
      if (!userId || submitting) return;
      setSubmitting(true);
      setError(null);
      try {
        const created = await accessRequestService.submit(reason);
        setRequest(created);
        await setUserCache(userId, USER_CACHE_SUFFIX.accessRequest, created);
        return created;
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Could not submit request";
        setError(msg);
        throw e;
      } finally {
        setSubmitting(false);
      }
    },
    [userId, submitting],
  );

  return {
    request,
    loading,
    submitting,
    error,
    reload: () => load({ background: true }),
    submit,
  };
}
