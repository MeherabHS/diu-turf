/**
 * Design tokens — derived from /app/design_guidelines.json.
 * Single source of truth for colours, typography, spacing, radii, shadows.
 */
import { Platform, TextStyle } from "react-native";

export const colors = {
  background: "#FFFFFF",
  surface: "#F8FAFC",
  surface_secondary: "#F1F5F9",
  primary: "#50B748",
  primary_dark: "#3B8C34",
  text_primary: "#0F172A",
  text_secondary: "#64748B",
  text_tertiary: "#94A3B8",
  border: "#E2E8F0",
  danger: "#DC2626",
  danger_bg: "#FEE2E2",
  status_available: "#50B748",
  status_available_bg: "#DCFCE7",
  status_booked: "#94A3B8",
  status_booked_bg: "#F1F5F9",
  status_maintenance: "#F59E0B",
  status_maintenance_bg: "#FEF3C7",
  status_selected: "#0F172A",
  status_selected_bg: "#E2E8F0",
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
  xxxl: 64,
} as const;

export const radii = {
  sm: 8,
  md: 12,
  lg: 16,
  pill: 9999,
} as const;

const systemFont = Platform.select({ ios: "System", android: "sans-serif", default: "System" });

export const typography: Record<string, TextStyle> = {
  h1: { fontSize: 44, fontWeight: "800", letterSpacing: -1.5, lineHeight: 52, fontFamily: systemFont },
  h2: { fontSize: 30, fontWeight: "700", letterSpacing: -1, lineHeight: 38, fontFamily: systemFont },
  h3: { fontSize: 22, fontWeight: "600", letterSpacing: -0.5, lineHeight: 30, fontFamily: systemFont },
  body: { fontSize: 16, fontWeight: "400", lineHeight: 24, fontFamily: systemFont },
  bodyBold: { fontSize: 16, fontWeight: "700", lineHeight: 24, fontFamily: systemFont },
  caption: { fontSize: 13, fontWeight: "400", lineHeight: 18, color: colors.text_secondary, fontFamily: systemFont },
  label: { fontSize: 11, fontWeight: "700", letterSpacing: 1.2, textTransform: "uppercase", fontFamily: systemFont },
};

export const shadows = {
  card: {
    shadowColor: "#0F172A",
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.04,
    shadowRadius: 24,
    elevation: 2,
  },
  button: {
    shadowColor: "#50B748",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.2,
    shadowRadius: 12,
    elevation: 4,
  },
} as const;

export const theme = { colors, spacing, radii, typography, shadows };
export type Theme = typeof theme;
