/** Notification history — list with mark-as-read. */
import { Ionicons } from "@expo/vector-icons";
import { Stack } from "expo-router";
import React, { useCallback, useMemo, useState } from "react";
import {
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";

import { Button } from "@/src/components/Button";
import { EmptyState } from "@/src/components/EmptyState";
import { ErrorState } from "@/src/components/ErrorState";
import { ScreenHeader } from "@/src/components/ScreenHeader";
import { SkeletonList } from "@/src/components/Skeleton";
import { useLiveScreenRefresh } from "@/src/hooks/useLiveScreenRefresh";
import { useSlowLoading } from "@/src/hooks/useSlowLoading";
import { notificationService } from "@/src/services/activityService";
import { colors, radii, spacing, typography } from "@/src/theme";
import type { NotificationItem } from "@/src/types/booking";
import { getFriendlyErrorMessage } from "@/src/utils/errors";

export default function NotificationsScreen() {
  const insets = useSafeAreaInsets();
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const slowLoading = useSlowLoading(loading && items.length === 0);

  const load = useCallback(async () => {
    try {
      const data = await notificationService.mine();
      setItems(data);
      setLoadError(null);
    } catch (e) {
      setLoadError(getFriendlyErrorMessage(e, "Unable to load. Try again."));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useLiveScreenRefresh(load);

  const markAll = async () => {
    await notificationService.markAllRead();
    await load();
  };
  const markOne = async (id: string) => {
    await notificationService.markRead(id);
    setItems((it) => it.map((n) => (n.notification_id === id ? { ...n, read: true } : n)));
  };

  const unreadCount = items.filter((n) => !n.read).length;

  const listHeader = useMemo(() => {
    if (unreadCount <= 0) return null;
    return (
      <View style={{ marginBottom: spacing.md }}>
        <Button label="Mark all as read" variant="secondary" onPress={markAll} testID="notifications-mark-all" />
      </View>
    );
  }, [unreadCount]);

  const listEmpty = useMemo(() => {
    if (slowLoading && loading) {
      return <Text style={styles.slowHint}>Still loading...</Text>;
    }
    if (loading && items.length === 0) {
      return <SkeletonList count={4} />;
    }
    if (loadError && items.length === 0) {
      return (
        <ErrorState
          message={loadError}
          onRetry={() => {
            setLoading(true);
            load();
          }}
          testID="notifications-load-error"
        />
      );
    }
    if (items.length === 0) {
      return (
        <EmptyState
          icon="notifications-off-outline"
          title="No notifications yet"
          subtitle="Booking updates will appear here."
          testID="notifications-empty"
        />
      );
    }
    return null;
  }, [slowLoading, loading, items.length, loadError, load]);

  return (
    <SafeAreaView style={styles.container} edges={["top"]} testID="notifications-screen">
      <Stack.Screen options={{ headerShown: false }} />
      <ScreenHeader
        eyebrow="NOTIFICATIONS"
        title="Inbox"
        subtitle={unreadCount > 0 ? `${unreadCount} unread` : "All caught up"}
      />
      <FlatList
        data={items}
        keyExtractor={(n) => n.notification_id}
        renderItem={({ item: n }) => (
          <TouchableOpacity
            onPress={() => !n.read && markOne(n.notification_id)}
            activeOpacity={0.85}
            style={[styles.item, !n.read && styles.itemUnread]}
            testID={`notification-${n.notification_id}`}
          >
            <View style={styles.itemTop}>
              <Text style={styles.title} numberOfLines={1}>{n.title}</Text>
              {!n.read ? <View style={styles.dot} /> : null}
            </View>
            <Text style={styles.msg}>{n.message}</Text>
            <Text style={styles.ts}>{new Date(n.created_at).toLocaleString()}</Text>
          </TouchableOpacity>
        )}
        ListHeaderComponent={listHeader}
        ListEmptyComponent={listEmpty}
        contentContainerStyle={[
          styles.scroll,
          { paddingBottom: insets.bottom + spacing.xxl },
          items.length === 0 && styles.scrollEmpty,
        ]}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => {
              setRefreshing(true);
              load();
            }}
            tintColor={colors.primary}
          />
        }
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  scroll: { paddingHorizontal: spacing.lg, paddingTop: spacing.sm },
  scrollEmpty: { flexGrow: 1 },
  slowHint: { ...typography.caption, color: colors.text_secondary, textAlign: "center", marginBottom: spacing.sm },
  item: {
    backgroundColor: colors.surface, borderRadius: radii.md, borderWidth: 1, borderColor: colors.border,
    padding: spacing.md, gap: 4, marginBottom: spacing.sm,
  },
  itemUnread: { backgroundColor: "#F0FDF4", borderColor: colors.status_available },
  itemTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  title: { ...typography.bodyBold, color: colors.text_primary, flex: 1 },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.primary, marginLeft: spacing.sm },
  msg: { ...typography.body, color: colors.text_secondary },
  ts: { ...typography.caption, marginTop: 2 },
});
