/** Guided empty state with optional action. */
import { Ionicons } from "@expo/vector-icons";
import React from "react";
import { StyleSheet, Text, View } from "react-native";

import { Button } from "@/src/components/Button";
import { Card } from "@/src/components/Card";
import { colors, spacing, typography } from "@/src/theme";

interface Props {
  icon?: React.ComponentProps<typeof Ionicons>["name"];
  title: string;
  subtitle: string;
  actionLabel?: string;
  onAction?: () => void;
  testID?: string;
}

export const EmptyState: React.FC<Props> = ({
  icon = "file-tray-outline",
  title,
  subtitle,
  actionLabel,
  onAction,
  testID = "empty-state",
}) => (
  <Card testID={testID}>
    <View style={styles.wrap}>
      <Ionicons name={icon} size={36} color={colors.text_tertiary} />
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.subtitle}>{subtitle}</Text>
      {actionLabel && onAction ? (
        <View style={{ width: "100%", marginTop: spacing.md }}>
          <Button label={actionLabel} onPress={onAction} testID={`${testID}-action`} />
        </View>
      ) : null}
    </View>
  </Card>
);

const styles = StyleSheet.create({
  wrap: { alignItems: "center", gap: spacing.sm, paddingVertical: spacing.md },
  title: { ...typography.h3, color: colors.text_primary, textAlign: "center" },
  subtitle: { ...typography.body, color: colors.text_secondary, textAlign: "center" },
});
