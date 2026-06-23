/**
 * Login screen — DIU email + password (Google Sign-In paused).
 */
import { Ionicons } from "@expo/vector-icons";
import { Link } from "expo-router";
import React, { useState } from "react";
import {
  Image,
  Linking,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Button } from "@/src/components/Button";
import { ADMIN_CONTACT_EMAIL, APP_NAME } from "@/src/constants";
import { useAuthStore } from "@/src/store/useAuthStore";
import { colors, radii, spacing, typography } from "@/src/theme";

const DEV_AUTH_ENABLED =
  __DEV__ && process.env.EXPO_PUBLIC_DEV_AUTH_ENABLED === "true";

export default function LoginScreen() {
  const loginWithPassword = useAuthStore((s) => s.loginWithPassword);
  const loginWithDev = useAuthStore((s) => s.loginWithDev);
  const isLoading = useAuthStore((s) => s.isLoading);
  const error = useAuthStore((s) => s.error);
  const setError = useAuthStore((s) => s.setError);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [devEmail, setDevEmail] = useState("261-35-113@diu.edu.bd");

  const handleLogin = async () => {
    setError(null);
    const trimmedEmail = email.trim().toLowerCase();
    if (!trimmedEmail) {
      setError("Enter your DIU email.");
      return;
    }
    if (!password) {
      setError("Enter your password.");
      return;
    }
    await loginWithPassword(trimmedEmail, password);
  };

  const handleDevLogin = async () => {
    setError(null);
    if (!devEmail.trim()) {
      setError("Enter a @diu.edu.bd email to use dev login.");
      return;
    }
    await loginWithDev(devEmail.trim().toLowerCase());
  };

  const contactAdmin = () => {
    const subject = encodeURIComponent("DIU Turf — account help");
    const body = encodeURIComponent(
      "Describe your issue (wrong student ID, login problem, etc.):\n\n",
    );
    Linking.openURL(`mailto:${ADMIN_CONTACT_EMAIL}?subject=${subject}&body=${body}`);
  };

  return (
    <SafeAreaView style={styles.container} edges={["top", "bottom"]} testID="login-screen">
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        <View style={styles.hero}>
          <Image
            source={{
              uri: "https://images.unsplash.com/photo-1517747614396-d21a78b850e8?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NTY2Nzd8MHwxfHNlYXJjaHwxfHxzb2NjZXIlMjB0dXJmfGVufDB8fHx8MTc4MTQxMTE5OHww&ixlib=rb-4.1.0&q=85&w=800",
            }}
            style={styles.heroImage}
          />
          <View style={styles.heroOverlay} />
          <View style={styles.heroContent}>
            <Text style={styles.eyebrow}>HOSTEL TURF</Text>
            <Text style={styles.brand} testID="login-brand">{APP_NAME}</Text>
          </View>
        </View>

        <View style={styles.body}>
          <Text style={styles.title} testID="login-title">Sign in to DIU Turf</Text>
          <Text style={styles.copy}>
            Sign in with your DIU student email and password.
          </Text>

          {error ? (
            <View style={styles.errorBox} testID="login-error">
              <Ionicons name="alert-circle" size={18} color={colors.danger} />
              <Text style={styles.errorText} numberOfLines={6}>{error}</Text>
            </View>
          ) : null}

          <Text style={styles.label}>DIU email</Text>
          <TextInput
            style={styles.input}
            value={email}
            onChangeText={(text) => {
              setEmail(text);
              setError(null);
            }}
            placeholder="261-35-113@diu.edu.bd or user@ds.diu.edu.bd"
            placeholderTextColor={colors.text_tertiary}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="email-address"
            textContentType="username"
            testID="login-email-input"
          />

          <Text style={styles.label}>Password</Text>
          <TextInput
            style={styles.input}
            value={password}
            onChangeText={(text) => {
              setPassword(text);
              setError(null);
            }}
            placeholder="Your password"
            placeholderTextColor={colors.text_tertiary}
            secureTextEntry
            autoCapitalize="none"
            autoCorrect={false}
            textContentType="password"
            testID="login-password-input"
          />

          <Button
            label="Sign in"
            onPress={handleLogin}
            loading={isLoading}
            testID="login-submit-button"
            leftIcon={<Ionicons name="log-in-outline" size={18} color="#FFFFFF" />}
          />

          <Link href="/(auth)/register" asChild>
            <Text style={styles.link} testID="login-create-account-link">
              Create account
            </Text>
          </Link>

          {DEV_AUTH_ENABLED ? (
            <View style={styles.devSection} testID="dev-login-section">
              <View style={styles.devDivider}>
                <View style={styles.devDividerLine} />
                <Text style={styles.devDividerText}>DEV ONLY</Text>
                <View style={styles.devDividerLine} />
              </View>
              <TextInput
                style={styles.devInput}
                value={devEmail}
                onChangeText={setDevEmail}
                placeholder="your-id@diu.edu.bd"
                placeholderTextColor={colors.text_tertiary}
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="email-address"
                testID="dev-email-input"
              />
              <Button
                label="Dev Login"
                onPress={handleDevLogin}
                loading={isLoading}
                testID="dev-login-button"
                leftIcon={<Ionicons name="code-slash" size={18} color="#FFFFFF" />}
              />
            </View>
          ) : null}

          <View style={styles.notice} testID="login-domain-notice">
            <Ionicons name="shield-checkmark-outline" size={16} color={colors.text_secondary} />
            <Text style={styles.noticeText}>
              Only DIU institutional emails are allowed (@diu.edu.bd and department addresses like @ds.diu.edu.bd).
            </Text>
          </View>

          <View style={styles.helpBox} testID="login-contact-admin">
            <Ionicons name="mail-outline" size={18} color={colors.primary} />
            <View style={styles.helpCopy}>
              <Text style={styles.helpTitle}>Need help signing in?</Text>
              <Text style={styles.helpText}>
                Contact the turf admin if your student ID or email was registered incorrectly.
              </Text>
              <TouchableOpacity onPress={contactAdmin} testID="login-contact-admin-button">
                <Text style={styles.helpLink}>Report an issue · {ADMIN_CONTACT_EMAIL}</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container:   { flex: 1, backgroundColor: colors.background },
  scroll:      { flexGrow: 1 },
  hero:        { height: 220, position: "relative", backgroundColor: colors.primary_dark },
  heroImage:   { ...StyleSheet.absoluteFillObject, resizeMode: "cover" },
  heroOverlay: { ...StyleSheet.absoluteFillObject, backgroundColor: "rgba(15,23,42,0.55)" },
  heroContent: { flex: 1, justifyContent: "flex-end", padding: spacing.lg },
  eyebrow:     { ...typography.label, color: "#FFFFFF", opacity: 0.85, marginBottom: spacing.xs },
  brand:       { ...typography.h1, color: "#FFFFFF" },
  body:        { padding: spacing.lg, gap: spacing.sm },
  title:       { ...typography.h2, color: colors.text_primary, marginBottom: spacing.xs },
  copy: {
    ...typography.body,
    color: colors.text_secondary,
    marginBottom: spacing.md,
  },
  label: {
    ...typography.caption,
    color: colors.text_secondary,
    fontWeight: "600",
    marginTop: spacing.xs,
  },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    ...typography.body,
    color: colors.text_primary,
    backgroundColor: colors.surface,
  },
  errorBox: {
    flexDirection: "row", alignItems: "flex-start", gap: spacing.sm,
    backgroundColor: colors.danger_bg, borderRadius: 12,
    padding: spacing.md, marginBottom: spacing.sm,
  },
  errorText:  { ...typography.body, color: colors.danger, flex: 1 },
  link: {
    ...typography.body,
    color: colors.primary,
    fontWeight: "600",
    textAlign: "center",
    marginTop: spacing.sm,
    paddingVertical: spacing.sm,
  },
  notice: {
    flexDirection: "row", alignItems: "flex-start", gap: spacing.sm,
    marginTop: spacing.md, paddingHorizontal: spacing.xs,
  },
  noticeText: { ...typography.caption, flex: 1 },
  bold:       { fontWeight: "700", color: colors.text_primary },
  helpBox: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: spacing.sm,
    marginTop: spacing.md,
    padding: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  helpCopy: { flex: 1, gap: spacing.xs },
  helpTitle: { ...typography.bodyBold, color: colors.text_primary },
  helpText: { ...typography.caption, color: colors.text_secondary },
  helpLink: { ...typography.caption, color: colors.primary, fontWeight: "600", marginTop: spacing.xs },
  devSection: { gap: spacing.sm, marginTop: spacing.md },
  devDivider: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  devDividerLine: { flex: 1, height: 1, backgroundColor: "#F59E0B44" },
  devDividerText: {
    ...typography.label,
    color: "#F59E0B",
    fontSize: 11,
    letterSpacing: 1.2,
  },
  devInput: {
    borderWidth: 1,
    borderColor: "#F59E0B66",
    borderRadius: 10,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    ...typography.body,
    color: colors.text_primary,
    backgroundColor: "#FEF3C710",
  },
});
