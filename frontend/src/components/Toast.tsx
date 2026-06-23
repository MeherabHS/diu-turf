/** Lightweight in-app Toast. Single message slot, auto-dismiss. */
import { Ionicons } from "@expo/vector-icons";
import React, { useEffect } from "react";
import { Animated, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { colors, radii, spacing, typography } from "@/src/theme";

type Kind = "success" | "error";
export interface ToastMessage {
  kind: Kind;
  text: string;
}

interface Props {
  message: ToastMessage | null;
  onHide: () => void;
  durationMs?: number;
}

export const Toast: React.FC<Props> = ({ message, onHide, durationMs = 2600 }) => {
  const insets = useSafeAreaInsets();
  const opacity = React.useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (!message) return;
    Animated.timing(opacity, { toValue: 1, duration: 200, useNativeDriver: true }).start();
    const t = setTimeout(() => {
      Animated.timing(opacity, { toValue: 0, duration: 200, useNativeDriver: true }).start(({ finished }) => {
        if (finished) onHide();
      });
    }, durationMs);
    return () => clearTimeout(t);
  }, [message, durationMs, onHide, opacity]);

  if (!message) return null;

  const isErr = message.kind === "error";
  return (
    <Animated.View
      pointerEvents="none"
      style={[
        styles.wrap,
        { top: insets.top + spacing.md, opacity },
      ]}
      testID={`toast-${message.kind}`}
    >
      <View style={[styles.pill, isErr ? styles.errBg : styles.okBg]}>
        <Ionicons
          name={isErr ? "alert-circle" : "checkmark-circle"}
          size={18}
          color={isErr ? colors.danger : colors.status_available}
        />
        <Text style={styles.text} numberOfLines={3}>{message.text}</Text>
      </View>
    </Animated.View>
  );
};

const styles = StyleSheet.create({
  wrap: { position: "absolute", left: spacing.md, right: spacing.md, alignItems: "center", zIndex: 100 },
  pill: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingVertical: spacing.sm + 2, paddingHorizontal: spacing.md,
    borderRadius: radii.pill,
    maxWidth: 520,
  },
  okBg: { backgroundColor: colors.status_available_bg },
  errBg: { backgroundColor: colors.danger_bg },
  text: { ...typography.bodyBold, color: colors.text_primary, flexShrink: 1 },
});
