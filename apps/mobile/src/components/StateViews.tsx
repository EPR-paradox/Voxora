import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

import { AppButton } from "./AppButton";
import { colors, spacing } from "../theme";
import { describeError, isRetryable } from "../api/errors";

export function LoadingView({ label = "加载中…" }: { label?: string }) {
  return (
    <View style={styles.center}>
      <ActivityIndicator color={colors.accent} />
      <Text style={styles.muted}>{label}</Text>
    </View>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <View style={styles.center}>
      <Text style={styles.title}>{title}</Text>
      {hint ? <Text style={styles.muted}>{hint}</Text> : null}
    </View>
  );
}

/**
 * The one place that turns a thrown error into something a learner can act on. The retry button only
 * appears when retrying could actually change the outcome (`isRetryable`), so a 404 never offers it.
 */
export function ErrorView({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const canRetry = onRetry !== undefined && isRetryable(error);
  return (
    <View style={styles.center}>
      <Text style={styles.title}>出错了</Text>
      <Text style={styles.muted}>{describeError(error)}</Text>
      {canRetry ? (
        <AppButton label="重试" variant="secondary" onPress={onRetry} style={styles.action} />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    padding: spacing.xl,
  },
  title: { color: colors.text, fontSize: 16, fontWeight: "600", textAlign: "center" },
  muted: { color: colors.textMuted, fontSize: 14, textAlign: "center", lineHeight: 20 },
  action: { marginTop: spacing.md, alignSelf: "stretch" },
});
