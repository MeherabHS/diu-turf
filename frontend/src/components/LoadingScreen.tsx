/** Full-screen loading — boot, auth restore, first dashboard load. */
import React from "react";
import { ActivityIndicator, Image, StyleSheet, Text, View } from "react-native";

import { APP_NAME } from "@/src/constants";
import { colors, spacing, typography } from "@/src/theme";

interface Props {
  title?: string;
  subtitle?: string;
  testID?: string;
}

export const LoadingScreen: React.FC<Props> = ({
  title = "Preparing your turf dashboard...",
  subtitle = "Please wait while we load your reservations.",
  testID = "loading-screen",
}) => (
  <View style={styles.wrap} testID={testID}>
    <Image
      source={{
        uri: "https://images.unsplash.com/photo-1556056504-5c7696c4c28d?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NTY2Nzd8MHwxfHNlYXJjaHwzfHxzb2NjZXIlMjB0dXJmfGVufDB8fHx8MTc4MTQxMTE5OHww&ixlib=rb-4.1.0&q=85&w=600",
      }}
      style={styles.bg}
    />
    <View style={styles.overlay} />
    <View style={styles.content}>
      <Text style={styles.brand}>{APP_NAME}</Text>
      <ActivityIndicator color="#FFFFFF" style={{ marginTop: spacing.lg }} />
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.subtitle}>{subtitle}</Text>
    </View>
  </View>
);

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: colors.primary, justifyContent: "center", alignItems: "center" },
  bg: { ...StyleSheet.absoluteFillObject, resizeMode: "cover", opacity: 0.25 },
  overlay: { ...StyleSheet.absoluteFillObject, backgroundColor: "rgba(15,23,42,0.35)" },
  content: { alignItems: "center", padding: spacing.xl, maxWidth: 320 },
  brand: { ...typography.h2, color: "#FFFFFF", textAlign: "center" },
  title: { ...typography.bodyBold, color: "#FFFFFF", textAlign: "center", marginTop: spacing.lg },
  subtitle: { ...typography.body, color: "#FFFFFF", opacity: 0.88, textAlign: "center", marginTop: spacing.sm },
});
