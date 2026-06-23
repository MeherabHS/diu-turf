/** Banner shown when the user can view slots but cannot book yet. */
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { colors, radii, spacing, typography } from "@/src/theme";

export function BookingAccessBanner({ compact }: { compact?: boolean }) {
  const router = useRouter();

  return (
    <Pressable
      style={[styles.box, compact && styles.boxCompact]}
      onPress={() => router.push("/request-access")}
      testID="booking-access-banner"
    >
      <Ionicons name="star-outline" size={22} color={colors.primary} />
      <View style={styles.copy}>
        <Text style={styles.title}>Booking access required</Text>
        <Text style={styles.body}>
          You can view turf availability. Request approval to reserve or cancel slots.
        </Text>
        <Text style={styles.link}>Request Booking Access</Text>
      </View>
      <Ionicons name="chevron-forward" size={18} color={colors.text_tertiary} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  box: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: spacing.sm,
    padding: spacing.md,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    marginBottom: spacing.md,
  },
  boxCompact: { marginBottom: spacing.sm },
  copy: { flex: 1, gap: spacing.xs },
  title: { ...typography.bodyBold, color: colors.text_primary },
  body: { ...typography.caption, color: colors.text_secondary },
  link: { ...typography.caption, color: colors.primary, fontWeight: "700", marginTop: spacing.xs },
});
