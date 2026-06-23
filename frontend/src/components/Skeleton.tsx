/** Shimmer-style skeleton placeholders for inline loading. */
import React, { useEffect, useRef } from "react";
import { Animated, StyleSheet, View, ViewStyle } from "react-native";

import { colors, radii, spacing } from "@/src/theme";

interface BoxProps {
  height?: number;
  width?: number | `${number}%`;
  style?: ViewStyle;
  testID?: string;
}

export const SkeletonBox: React.FC<BoxProps> = ({
  height = 16,
  width = "100%",
  style,
  testID,
}) => {
  const opacity = useRef(new Animated.Value(0.45)).current;

  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 0.9, duration: 700, useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 0.45, duration: 700, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [opacity]);

  return (
    <Animated.View
      style={[styles.box, { height, width, opacity }, style]}
      testID={testID}
    />
  );
};

export const SkeletonCard: React.FC<{ lines?: number; testID?: string }> = ({
  lines = 3,
  testID = "skeleton-card",
}) => (
  <View style={styles.card} testID={testID}>
    <SkeletonBox height={12} width="40%" />
    <SkeletonBox height={20} width="70%" style={{ marginTop: spacing.sm }} />
    {Array.from({ length: lines - 2 }).map((_, i) => (
      <SkeletonBox key={i} height={14} width="90%" style={{ marginTop: spacing.sm }} />
    ))}
  </View>
);

export const SkeletonList: React.FC<{ count?: number; testID?: string }> = ({
  count = 3,
  testID = "skeleton-list",
}) => (
  <View style={{ gap: spacing.sm }} testID={testID}>
    {Array.from({ length: count }).map((_, i) => (
      <View key={i} style={styles.row}>
        <SkeletonBox height={48} width={48} style={styles.avatar} />
        <View style={{ flex: 1, gap: spacing.sm }}>
          <SkeletonBox height={14} width="60%" />
          <SkeletonBox height={12} width="40%" />
        </View>
      </View>
    ))}
  </View>
);

export const SkeletonSlotCards: React.FC<{ count?: number }> = ({ count = 3 }) => (
  <View style={{ gap: spacing.sm }}>
    {Array.from({ length: count }).map((_, i) => (
      <View key={i} style={styles.slotCard}>
        <SkeletonBox height={18} width="50%" />
        <SkeletonBox height={14} width="35%" style={{ marginTop: spacing.sm }} />
        <SkeletonBox height={48} width="100%" style={{ marginTop: spacing.md, borderRadius: radii.pill }} />
      </View>
    ))}
  </View>
);

const styles = StyleSheet.create({
  box: { backgroundColor: colors.surface_secondary, borderRadius: radii.sm },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    padding: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  avatar: { borderRadius: radii.sm },
  slotCard: {
    padding: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: 16,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
});
