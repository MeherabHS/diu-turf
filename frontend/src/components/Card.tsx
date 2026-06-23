/** Reusable card surface. */
import React from "react";
import { StyleSheet, View, ViewStyle } from "react-native";

import { colors, radii, shadows, spacing } from "@/src/theme";

interface Props {
  children: React.ReactNode;
  style?: ViewStyle;
  testID?: string;
}

export const Card: React.FC<Props> = ({ children, style, testID }) => (
  <View style={[styles.card, style]} testID={testID}>
    {children}
  </View>
);

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    ...shadows.card,
  },
});
