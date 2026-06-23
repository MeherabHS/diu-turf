/** Per-user AsyncStorage cache — keys scoped by user id to prevent cross-account leaks. */
import { storage } from "@/src/utils/storage";

const PREFIX = "@diu/user-cache";

export function userCacheKey(userId: string, suffix: string): string {
  return `${PREFIX}:${userId}:${suffix}`;
}

export async function getUserCache<T>(
  userId: string,
  suffix: string,
  fallback: T,
): Promise<T | null> {
  if (!userId) return fallback;
  return storage.getItem(userCacheKey(userId, suffix), fallback);
}

export async function setUserCache<T extends string | number | boolean | null>(
  userId: string,
  suffix: string,
  value: T,
): Promise<void> {
  if (!userId) return;
  await storage.setItem(userCacheKey(userId, suffix), value);
}

export async function clearUserCache(userId: string | null | undefined): Promise<void> {
  if (!userId) return;
  await Promise.all([
    storage.removeItem(userCacheKey(userId, "access_request")),
  ]);
}

export const USER_CACHE_SUFFIX = {
  accessRequest: "access_request",
} as const;
