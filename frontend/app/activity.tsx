/** Activity feed — newest first, live-updated via WS. */
import { Ionicons } from "@expo/vector-icons";
import { Stack } from "expo-router";
import React, { useCallback, useMemo, useState } from "react";
import { FlatList, RefreshControl, StyleSheet, Text, View } from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";

import { EmptyState } from "@/src/components/EmptyState";
import { ErrorState } from "@/src/components/ErrorState";
import { ScreenHeader } from "@/src/components/ScreenHeader";
import { SkeletonList } from "@/src/components/Skeleton";
import { useLiveScreenRefresh } from "@/src/hooks/useLiveScreenRefresh";
import { useSlowLoading } from "@/src/hooks/useSlowLoading";
import { activityService } from "@/src/services/activityService";
import { colors, radii, spacing, typography } from "@/src/theme";
import type { ActivityItem } from "@/src/types/booking";
import { getActivityDisplayText, isMeaningfulActivity } from "@/src/utils/activityText";
import { getFriendlyErrorMessage } from "@/src/utils/errors";

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

export default function ActivityScreen() {
  const insets = useSafeAreaInsets();
  const [items, setItems] = useState<ActivityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const slowLoading = useSlowLoading(loading && items.length === 0);

  const load = useCallback(async () => {
    try {
      const data = await activityService.recent(20);
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

  const visibleItems = useMemo(
    () => items.filter(isMeaningfulActivity),
    [items],
  );

  const listEmpty = useMemo(() => {
    if (loading && items.length === 0) {
      return <SkeletonList count={5} />;
    }
    if (loadError && items.length === 0) {
      return (
        <ErrorState
          message={loadError}
          onRetry={() => {
            setLoading(true);
            setLoadError(null);
            load();
          }}
          testID="activity-load-error"
        />
      );
    }
    if (visibleItems.length === 0) {
      return (
        <EmptyState
          icon="pulse-outline"
          title="No recent activity yet"
          subtitle="Your booking updates will appear here."
          testID="activity-empty"
        />
      );
    }
    return null;
  }, [loading, items.length, loadError, visibleItems.length, load]);

  return (
    <SafeAreaView style={styles.container} edges={["top"]} testID="activity-screen">
      <Stack.Screen options={{ headerShown: false }} />
      <ScreenHeader eyebrow="ACTIVITY FEED" title="Recent events" subtitle="Newest first · updates live." />
      {slowLoading && loading ? (
        <Text style={styles.slowHint}>Still loading...</Text>
      ) : null}
      <FlatList
        data={visibleItems}
        keyExtractor={(item) => item.activity_id}
        renderItem={({ item }) => <ActivityRow item={item} />}
        contentContainerStyle={[
          styles.scroll,
          { paddingBottom: insets.bottom + spacing.xxl },
          visibleItems.length === 0 && styles.scrollEmpty,
        ]}
        ListEmptyComponent={listEmpty}
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

const ActivityRow: React.FC<{ item: ActivityItem }> = ({ item }) => {
  const text = getActivityDisplayText(item);
  if (!text) return null;
  const iconName: React.ComponentProps<typeof Ionicons>["name"] =
    item.action === "BOOKED" ? "checkmark-circle" :
    item.action === "CANCELLED" ? "close-circle" :
    "ellipse";
  const iconColor =
    item.action === "BOOKED" ? colors.status_available :
    item.action === "CANCELLED" ? colors.danger :
    colors.text_tertiary;
  return (
    <View style={styles.row} testID={`activity-row-${item.activity_id}`}>
      <Ionicons name={iconName} size={22} color={iconColor} style={{ marginTop: 2 }} />
      <View style={{ flex: 1 }}>
        <Text style={styles.text} numberOfLines={3}>{text}</Text>
        <Text style={styles.ago}>{timeAgo(item.created_at)}</Text>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  scroll: { paddingHorizontal: spacing.lg, paddingTop: spacing.sm, gap: spacing.sm },
  scrollEmpty: { flexGrow: 1 },
  slowHint: { ...typography.caption, color: colors.text_secondary, textAlign: "center", marginBottom: spacing.sm },
  row: {
    flexDirection: "row", alignItems: "flex-start", gap: spacing.md,
    paddingVertical: spacing.md, paddingHorizontal: spacing.md,
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
    borderRadius: radii.md, marginBottom: spacing.sm,
  },
  text: { ...typography.body, color: colors.text_primary },
  ago: { ...typography.caption, marginTop: 2 },
});
