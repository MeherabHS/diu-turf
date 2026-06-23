/** Status chip — colour-coded by slot status. */
import React from "react";
import { StyleSheet, Text, View } from "react-native";

import { colors, radii, spacing, typography } from "@/src/theme";
import type { SlotStatus } from "@/src/types";

interface Props {
  status: SlotStatus | "selected";
  testID?: string;
}

const MAP: Record<Props["status"], { bg: string; fg: string; label: string }> = {
  available:   { bg: colors.status_available_bg,    fg: colors.status_available,    label: "Available" },
  booked:      { bg: colors.status_booked_bg,       fg: colors.status_booked,       label: "Booked" },
  completed:   { bg: colors.status_booked_bg,       fg: colors.status_booked,       label: "Completed" },
  maintenance: { bg: colors.status_maintenance_bg,  fg: colors.status_maintenance,  label: "Maintenance" },
  selected:    { bg: colors.status_selected_bg,     fg: colors.status_selected,     label: "Selected" },
};

export const StatusChip: React.FC<Props> = ({ status, testID }) => {
  const cfg = MAP[status];
  return (
    <View style={[styles.chip, { backgroundColor: cfg.bg }]} testID={testID}>
      <Text style={[styles.text, { color: cfg.fg }]}>{cfg.label}</Text>
    </View>
  );
};

const styles = StyleSheet.create({
  chip: {
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: radii.pill,
    alignSelf: "flex-start",
  },
  text: { ...typography.label, fontSize: 11 },
});
