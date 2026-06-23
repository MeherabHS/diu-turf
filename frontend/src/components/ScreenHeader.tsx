/** Sticky page header. */
import React from "react";
import { StyleSheet, Text, View } from "react-native";

import { colors, spacing, typography } from "@/src/theme";

interface Props {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  right?: React.ReactNode;
  testID?: string;
}

export const ScreenHeader: React.FC<Props> = ({ eyebrow, title, subtitle, right, testID }) => (
  <View style={styles.wrap} testID={testID}>
    <View style={styles.row}>
      <View style={styles.flex}>
        {eyebrow ? <Text style={styles.eyebrow}>{eyebrow}</Text> : null}
        <Text style={styles.title} numberOfLines={2}>{title}</Text>
        {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
      </View>
      {right}
    </View>
  </View>
);

const styles = StyleSheet.create({
  wrap: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.lg,
    paddingBottom: spacing.md,
    backgroundColor: colors.background,
  },
  row: { flexDirection: "row", alignItems: "flex-start" },
  flex: { flex: 1 },
  eyebrow: { ...typography.label, color: colors.text_secondary, marginBottom: spacing.xs },
  title: { ...typography.h2, color: colors.text_primary },
  subtitle: { ...typography.body, color: colors.text_secondary, marginTop: spacing.xs },
});
