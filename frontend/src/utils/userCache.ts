/** Per-user AsyncStorage cache â€” keys scoped by user id to prevent cross-account leaks. */
import { storage } from "@/src/utils/storage";
import type { StorageItemValue } from "@/src/utils/storage/storage-base";

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
  return storage.getItem(userCacheKey(userId, suffix), fallback as StorageItemValue) as Promise<T | null>;
}

export async function setUserCache<T>(
  userId: string,
  suffix: string,
  value: T,
): Promise<void> {
  if (!userId) return;
  await storage.setItem(userCacheKey(userId, suffix), value as StorageItemValue);
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

