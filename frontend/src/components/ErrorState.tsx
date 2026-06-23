/** Inline error with optional retry — never shows raw HTTP errors. */
import { Ionicons } from "@expo/vector-icons";
import React from "react";
import { StyleSheet, Text, View } from "react-native";

import { Button } from "@/src/components/Button";
import { Card } from "@/src/components/Card";
import { colors, spacing, typography } from "@/src/theme";

interface Props {
  message: string;
  hint?: string;
  onRetry?: () => void;
  retrying?: boolean;
  testID?: string;
}

export const ErrorState: React.FC<Props> = ({
  message,
  hint,
  onRetry,
  retrying,
  testID = "error-state",
}) => (
  <Card testID={testID}>
    <View style={styles.wrap}>
      <Ionicons name="alert-circle-outline" size={32} color={colors.danger} />
      <Text style={styles.message}>{message}</Text>
      {hint ? <Text style={styles.hint}>{hint}</Text> : null}
      {onRetry ? (
        <View style={{ width: "100%", marginTop: spacing.md }}>
          <Button
            label="Retry"
            variant="secondary"
            onPress={onRetry}
            loading={retrying}
            testID={`${testID}-retry`}
          />
        </View>
      ) : null}
    </View>
  </Card>
);

const styles = StyleSheet.create({
  wrap: { alignItems: "center", gap: spacing.sm, paddingVertical: spacing.sm },
  message: { ...typography.bodyBold, color: colors.text_primary, textAlign: "center" },
  hint: { ...typography.caption, color: colors.text_secondary, textAlign: "center" },
});
