import { ActivityIndicator, Pressable, StyleSheet, Text, type ViewStyle } from "react-native";

import { colors, radius, spacing } from "../theme";

interface AppButtonProps {
  label: string;
  onPress: () => void;
  variant?: "primary" | "secondary" | "danger";
  disabled?: boolean;
  busy?: boolean;
  style?: ViewStyle;
}

/**
 * One button for the whole app: press feedback, a busy spinner that also blocks a second tap, and the
 * disabled look. Screens pass `busy` while a request is in flight instead of disabling on their own, so
 * "cannot submit twice" (design §10.3) is impossible to forget.
 */
export function AppButton({
  label,
  onPress,
  variant = "primary",
  disabled = false,
  busy = false,
  style,
}: AppButtonProps) {
  const blocked = disabled || busy;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: blocked, busy }}
      disabled={blocked}
      onPress={onPress}
      style={({ pressed }) => [
        styles.base,
        styles[variant],
        pressed && !blocked && styles.pressed,
        blocked && styles.blocked,
        style,
      ]}
    >
      {busy ? <ActivityIndicator color={colors.text} size="small" /> : null}
      <Text style={[styles.label, variant === "secondary" && styles.secondaryLabel]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    minHeight: 46,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.md,
  },
  primary: { backgroundColor: colors.accent },
  secondary: { backgroundColor: colors.surfaceMuted, borderWidth: 1, borderColor: colors.border },
  danger: { backgroundColor: colors.danger },
  pressed: { opacity: 0.85 },
  blocked: { opacity: 0.45 },
  label: { color: colors.text, fontSize: 15, fontWeight: "600" },
  secondaryLabel: { color: colors.text },
});
