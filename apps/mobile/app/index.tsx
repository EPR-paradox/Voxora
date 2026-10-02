import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { AppButton } from "../src/components/AppButton";
import { Card } from "../src/components/Card";
import { Screen } from "../src/components/Screen";
import { getSession } from "../src/features/practice/api";
import { clearLastSessionId, getLastSessionId } from "../src/storage";
import { API_BASE_URL } from "../src/api/client";
import { colors, spacing, typography } from "../src/theme";

/**
 * Home. There is no "list my sessions" endpoint yet, so "continue" is driven by the session id kept in
 * local storage — and re-checked against the server on every focus, because a session finished on another
 * device must not offer a resume button here.
 */
export default function HomeScreen() {
  const router = useRouter();
  const [resumableSessionId, setResumableSessionId] = useState<string | null>(null);

  useFocusEffect(
    useCallback(() => {
      let cancelled = false;
      void (async () => {
        const stored = await getLastSessionId();
        if (!stored) {
          if (!cancelled) setResumableSessionId(null);
          return;
        }
        try {
          const session = await getSession(stored);
          if (cancelled) return;
          if (session.status === "active") {
            setResumableSessionId(stored);
          } else {
            await clearLastSessionId();
            setResumableSessionId(null);
          }
        } catch {
          if (!cancelled) setResumableSessionId(null);
        }
      })();
      return () => {
        cancelled = true;
      };
    }, []),
  );

  return (
    <Screen>
      <View style={styles.header}>
        <Text style={styles.hero}>用英语把工作说清楚</Text>
        <Text style={styles.heroHint}>
          半导体行业的面试、会议、出差场景。练的是表达，不是技术结论。
        </Text>
      </View>

      {resumableSessionId ? (
        <Card title="上次练到一半" subtitle="接着说完，或者结束后直接生成反馈。">
          <AppButton
            label="继续这次练习"
            onPress={() =>
              router.push({
                pathname: "/practice/[sessionId]",
                params: { sessionId: resumableSessionId },
              })
            }
          />
        </Card>
      ) : null}

      <View style={styles.actions}>
        <AppButton
          label="开始一次新练习"
          onPress={() => router.push("/scenarios")}
          style={styles.primaryAction}
        />
        <AppButton label="复习列表" variant="secondary" onPress={() => router.push("/review")} />
        <AppButton label="设置" variant="secondary" onPress={() => router.push("/settings")} />
      </View>

      <Text style={styles.footer}>后端：{API_BASE_URL}</Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: { gap: spacing.sm, marginBottom: spacing.xl },
  hero: { ...typography.title, color: colors.text },
  heroHint: { ...typography.body, color: colors.textMuted, lineHeight: 22 },
  actions: { gap: spacing.md },
  primaryAction: { marginBottom: spacing.xs },
  footer: { marginTop: spacing.xxl, ...typography.caption, color: colors.textMuted },
});
