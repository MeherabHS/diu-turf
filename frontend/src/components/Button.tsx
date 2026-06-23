/** Primary action button — pill-shaped, design-system compliant. */
import React from "react";
import {
  ActivityIndicator,
  StyleSheet,
  Text,
  TouchableOpacity,
  TouchableOpacityProps,
  View,
  ViewStyle,
} from "react-native";

import { colors, radii, shadows, spacing, typography } from "@/src/theme";

type Variant = "primary" | "secondary" | "ghost";

interface Props extends Omit<TouchableOpacityProps, "style"> {
  label: string;
  /** Shown while loading (e.g. "Booking..."). Defaults to label. */
  loadingLabel?: string;
  variant?: Variant;
  loading?: boolean;
  fullWidth?: boolean;
  testID: string;
  leftIcon?: React.ReactNode;
  style?: ViewStyle;
}

export const Button: React.FC<Props> = ({
  label,
  loadingLabel,
  variant = "primary",
  loading = false,
  fullWidth = true,
  disabled,
  leftIcon,
  style,
  testID,
  ...rest
}) => {
  const isDisabled = disabled || loading;
  const containerStyle = [
    styles.base,
    fullWidth && styles.fullWidth,
    variant === "primary" && styles.primary,
    variant === "secondary" && styles.secondary,
    variant === "ghost" && styles.ghost,
    isDisabled && styles.disabled,
    style,
  ];
  const textStyle = [
    styles.text,
    variant === "primary" && styles.textPrimary,
    variant === "secondary" && styles.textSecondary,
    variant === "ghost" && styles.textGhost,
  ];
  return (
    <TouchableOpacity
      accessibilityRole="button"
      activeOpacity={0.85}
      disabled={isDisabled}
      style={containerStyle}
      testID={testID}
      {...rest}
    >
      {loading ? (
        <ActivityIndicator color={variant === "primary" ? "#fff" : colors.text_primary} />
      ) : (
        <View style={styles.row}>
          {leftIcon ? <View style={styles.icon}>{leftIcon}</View> : null}
          <Text style={textStyle}>{loading ? (loadingLabel ?? label) : label}</Text>
        </View>
      )}
    </TouchableOpacity>
  );
};

const styles = StyleSheet.create({
  base: {
    minHeight: 56,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.xl,
    borderRadius: radii.pill,
    alignItems: "center",
    justifyContent: "center",
  },
  fullWidth: { alignSelf: "stretch" },
  primary: { backgroundColor: colors.primary, ...shadows.button },
  secondary: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  ghost: { backgroundColor: "transparent" },
  disabled: { opacity: 0.5 },
  row: { flexDirection: "row", alignItems: "center" },
  icon: { marginRight: spacing.sm },
  text: { ...typography.bodyBold, fontSize: 16 },
  textPrimary: { color: "#FFFFFF" },
  textSecondary: { color: colors.text_primary },
  textGhost: { color: colors.text_primary },
});
