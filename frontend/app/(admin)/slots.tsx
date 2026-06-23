/** Admin > Slot management — add, edit, disable, and enable turf time slots. */
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import React, { useCallback, useEffect, useState } from "react";
import {
  FlatList,
  Modal,
  RefreshControl,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";

import { Button } from "@/src/components/Button";
import { EmptyState } from "@/src/components/EmptyState";
import { ScreenHeader } from "@/src/components/ScreenHeader";
import { SkeletonList } from "@/src/components/Skeleton";
import { Toast, type ToastMessage } from "@/src/components/Toast";
import { adminService, type AdminSlotRow } from "@/src/services/adminService";
import { colors, radii, spacing, typography } from "@/src/theme";
import { getFriendlyErrorMessage } from "@/src/utils/errors";

function formatTimeRange(start: string, end: string): string {
  const fmt = (value: string) => {
    const [h, m] = value.split(":").map((part) => Number(part));
    const date = new Date(2000, 0, 1, h, m);
    return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  };
  return `${fmt(start)} – ${fmt(end)}`;
}

function validateLocalTimes(start: string, end: string): string | null {
  const timeRe = /^([01]\d|2[0-3]):[0-5]\d$/;
  if (!timeRe.test(start.trim()) || !timeRe.test(end.trim())) {
    return "Use HH:MM format (e.g. 19:00).";
  }
  if (start.trim() >= end.trim()) {
    return "Start time must be before end time.";
  }
  return null;
}

export default function AdminSlotsScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [items, setItems] = useState<AdminSlotRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const [formModal, setFormModal] = useState<"add" | "edit" | null>(null);
  const [editing, setEditing] = useState<AdminSlotRow | null>(null);
  const [slotKey, setSlotKey] = useState("");
  const [startTime, setStartTime] = useState("");
  const [endTime, setEndTime] = useState("");

  const load = useCallback(async () => {
    try {
      const data = await adminService.listSlots();
      setItems(data);
    } catch (e) {
      setToast({ kind: "error", text: getFriendlyErrorMessage(e) });
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    load();
  }, [load]);

  const openAdd = () => {
    setEditing(null);
    setSlotKey("");
    setStartTime("");
    setEndTime("");
    setFormModal("add");
  };

  const openEdit = (slot: AdminSlotRow) => {
    setEditing(slot);
    setSlotKey(slot.slot_key);
    setStartTime(slot.start_time);
    setEndTime(slot.end_time);
    setFormModal("edit");
  };

  const closeForm = () => {
    if (submitting) return;
    setFormModal(null);
    setEditing(null);
  };

  const saveSlot = async () => {
    const key = slotKey.trim().toUpperCase();
    const start = startTime.trim();
    const end = endTime.trim();
    const localError = validateLocalTimes(start, end);
    if (!key) {
      setToast({ kind: "error", text: "Slot key is required." });
      return;
    }
    if (localError) {
      setToast({ kind: "error", text: localError });
      return;
    }

    setSubmitting(true);
    try {
      if (formModal === "add") {
        await adminService.createSlot({ slot_key: key, start_time: start, end_time: end });
        setToast({ kind: "success", text: `Slot ${key} created` });
      } else if (editing) {
        await adminService.updateSlot(editing.id, {
          slot_key: key,
          start_time: start,
          end_time: end,
          is_active: editing.is_active,
        });
        setToast({ kind: "success", text: `Slot ${key} updated` });
      }
      setFormModal(null);
      setEditing(null);
      await load();
    } catch (e) {
      setToast({ kind: "error", text: getFriendlyErrorMessage(e) });
    } finally {
      setSubmitting(false);
    }
  };

  const toggleActive = async (slot: AdminSlotRow) => {
    setSubmitting(true);
    try {
      if (slot.is_active) {
        await adminService.disableSlot(slot.id);
        setToast({ kind: "success", text: `Slot ${slot.slot_key} disabled` });
      } else {
        await adminService.enableSlot(slot.id);
        setToast({ kind: "success", text: `Slot ${slot.slot_key} enabled` });
      }
      await load();
    } catch (e) {
      setToast({ kind: "error", text: getFriendlyErrorMessage(e) });
    } finally {
      setSubmitting(false);
    }
  };

  const renderRow = ({ item }: { item: AdminSlotRow }) => {
    const active = item.is_active;
    return (
      <View style={styles.row} testID={`slot-row-${item.slot_key}`}>
        <View style={styles.rowMain}>
          <Text style={styles.rowTitle}>Slot {item.slot_key}</Text>
          <Text style={styles.rowMeta}>{formatTimeRange(item.start_time, item.end_time)}</Text>
          <View style={[styles.badge, active ? styles.badgeActive : styles.badgeDisabled]}>
            <Text style={[styles.badgeText, active ? styles.badgeTextActive : styles.badgeTextDisabled]}>
              {active ? "Active" : "Disabled"}
            </Text>
          </View>
        </View>
        <View style={styles.rowActions}>
          <TouchableOpacity
            onPress={() => openEdit(item)}
            style={styles.iconBtn}
            disabled={submitting}
            testID={`slot-edit-${item.slot_key}`}
          >
            <Text style={styles.actionLabel}>Edit</Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={() => void toggleActive(item)}
            style={styles.iconBtn}
            disabled={submitting}
            testID={active ? `slot-disable-${item.slot_key}` : `slot-enable-${item.slot_key}`}
          >
            <Text style={[styles.actionLabel, active ? styles.disableLabel : styles.enableLabel]}>
              {active ? "Disable" : "Enable"}
            </Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  };

  return (
    <SafeAreaView style={styles.container} edges={["top"]} testID="admin-slots-screen">
      <Toast message={toast} onHide={() => setToast(null)} />
      <ScreenHeader
        eyebrow="ADMIN · SLOTS"
        title="Manage slots"
        subtitle="Main Turf time windows"
        right={
          <TouchableOpacity onPress={() => router.back()} style={styles.backBtn} testID="slots-back">
            <Ionicons name="arrow-back" size={22} color={colors.text_primary} />
          </TouchableOpacity>
        }
      />

      <View style={styles.toolbar}>
        <Button label="Add slot" onPress={openAdd} testID="slots-add-button" fullWidth={false} style={styles.addBtn} />
      </View>

      {loading && items.length === 0 ? (
        <View style={{ paddingHorizontal: spacing.lg }}>
          <SkeletonList count={4} />
        </View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(item) => item.id}
          renderItem={renderRow}
          contentContainerStyle={{ paddingHorizontal: spacing.lg, paddingBottom: insets.bottom + spacing.xxl }}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={colors.primary} />
          }
          ListEmptyComponent={
            !loading ? (
              <EmptyState icon="time-outline" title="No slots yet" subtitle="Add a slot to get started." testID="slots-empty" />
            ) : null
          }
        />
      )}

      <Modal visible={formModal !== null} transparent animationType="fade" onRequestClose={closeForm}>
        <View style={styles.modalBackdrop} testID="slot-form-modal">
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>{formModal === "add" ? "Add slot" : "Edit slot"}</Text>
            <Text style={styles.modalLabel}>Slot key</Text>
            <TextInput
              value={slotKey}
              onChangeText={setSlotKey}
              placeholder="D"
              autoCapitalize="characters"
              autoCorrect={false}
              style={styles.input}
              testID="slot-key-input"
            />
            <Text style={styles.modalLabel}>Start time (HH:MM)</Text>
            <TextInput
              value={startTime}
              onChangeText={setStartTime}
              placeholder="19:00"
              autoCapitalize="none"
              style={styles.input}
              testID="slot-start-input"
            />
            <Text style={styles.modalLabel}>End time (HH:MM)</Text>
            <TextInput
              value={endTime}
              onChangeText={setEndTime}
              placeholder="20:00"
              autoCapitalize="none"
              style={styles.input}
              testID="slot-end-input"
            />
            <View style={{ height: spacing.lg }} />
            <Button
              label="Save"
              onPress={() => void saveSlot()}
              loading={submitting}
              testID="slot-save-button"
            />
            <View style={{ height: spacing.sm }} />
            <Button label="Cancel" variant="ghost" onPress={closeForm} disabled={submitting} testID="slot-cancel-button" />
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  backBtn: { padding: spacing.xs },
  toolbar: { paddingHorizontal: spacing.lg, marginBottom: spacing.md },
  addBtn: { alignSelf: "flex-start" },
  row: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    padding: spacing.md,
    marginBottom: spacing.sm,
    backgroundColor: colors.surface,
  },
  rowMain: { marginBottom: spacing.sm },
  rowTitle: { ...typography.bodyBold, color: colors.text_primary },
  rowMeta: { ...typography.body, color: colors.text_secondary, marginTop: 4 },
  badge: {
    alignSelf: "flex-start",
    marginTop: spacing.sm,
    borderRadius: radii.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
  },
  badgeActive: { backgroundColor: colors.status_available_bg },
  badgeDisabled: { backgroundColor: colors.status_booked_bg },
  badgeText: { ...typography.label, fontSize: 10 },
  badgeTextActive: { color: colors.status_available },
  badgeTextDisabled: { color: colors.status_booked },
  rowActions: { flexDirection: "row", gap: spacing.md },
  iconBtn: { paddingVertical: spacing.xs },
  actionLabel: { ...typography.bodyBold, color: colors.primary, fontSize: 14 },
  disableLabel: { color: colors.status_maintenance },
  enableLabel: { color: colors.status_available },
  modalBackdrop: {
    flex: 1,
    backgroundColor: "rgba(15,23,42,0.55)",
    justifyContent: "center",
    padding: spacing.lg,
  },
  modalCard: { backgroundColor: colors.background, borderRadius: radii.lg, padding: spacing.lg },
  modalTitle: { ...typography.h2, color: colors.text_primary, marginBottom: spacing.md },
  modalLabel: { ...typography.label, color: colors.text_secondary, marginTop: spacing.sm, marginBottom: spacing.xs },
  input: {
    minHeight: 48,
    backgroundColor: colors.surface_secondary,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    fontSize: 16,
    color: colors.text_primary,
  },
});
