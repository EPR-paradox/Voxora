import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { AppButton } from "../src/components/AppButton";
import { Card } from "../src/components/Card";
import { Screen } from "../src/components/Screen";
import { ErrorView, LoadingView } from "../src/components/StateViews";
import { API_BASE_URL } from "../src/api/client";
import type { PracticeSessionSummary } from "../src/api/types";
import { listSessions } from "../src/features/practice/api";
import { colors, spacing, typography } from "../src/theme";

const HISTORY_PREVIEW = 5;

/**
 * Home. Everything here comes from the server's history endpoint, so "continue" is correct across
 * devices and after a reinstall — a session id kept only in local storage would not be.
 */
export default function HomeScreen() {
  const router = useRouter();
  const history = useQuery({
    queryKey: ["session-history"],
    queryFn: () => listSessions({ limit: HISTORY_PREVIEW }),
  });

  const activeSession = history.data?.items.find((item) => item.status === "active");
  const recent = history.data?.items.filter((item) => item.status !== "active") ?? [];

  function openSession(item: PracticeSessionSummary) {
    if (item.status === "active") {
      router.push({ pathname: "/practice/[sessionId]", params: { sessionId: item.id } });
      return;
    }
    // Finished sessions have (or failed to have) a report: that is the screen worth opening.
    router.push({ pathname: "/evaluation/[sessionId]", params: { sessionId: item.id } });
  }

  return (
    <Screen>
      <View style={styles.header}>
        <Text style={styles.hero}>把技术讲清楚，把机会拿下来</Text>
        <Text style={styles.heroHint}>
          面试、技术会议、客户沟通、出差、旅游等真实场景逐轮对练。每场结束给你一份基于原话的英语改进清单。
        </Text>
      </View>

      {history.isPending ? <LoadingView label="正在看你的练习记录…" /> : null}
      {history.isError ? (
        <ErrorView error={history.error} onRetry={() => void history.refetch()} />
      ) : null}

      {activeSession ? (
        <Card title="上次练到一半" subtitle={activeSession.scenario.title}>
          <Text style={styles.muted}>
            聊了 {activeSession.turn_count} 轮 · {formatRelative(activeSession.last_activity_at)}
          </Text>
          <AppButton label="继续这次练习" onPress={() => openSession(activeSession)} />
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

      {recent.length > 0 ? (
        <View style={styles.history}>
          <Text style={styles.sectionTitle}>最近练习</Text>
          {recent.map((item) => (
            <Pressable key={item.id} onPress={() => openSession(item)}>
              <Card style={styles.historyItem}>
                <Text style={styles.historyTitle}>{item.scenario.title}</Text>
                <Text style={styles.muted}>
                  {item.evaluation_status === "completed" ? "有反馈 · " : ""}
                  {item.turn_count} 轮 · {formatRelative(item.last_activity_at)}
                </Text>
              </Card>
            </Pressable>
          ))}
        </View>
      ) : null}

      <Text style={styles.footer}>后端：{API_BASE_URL}</Text>
    </Screen>
  );
}

function formatRelative(iso: string): string {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  return `${Math.round(hours / 24)} 天前`;
}

const styles = StyleSheet.create({
  header: { gap: spacing.sm, marginBottom: spacing.xl },
  hero: { ...typography.title, color: colors.text },
  heroHint: { ...typography.body, color: colors.textMuted, lineHeight: 22 },
  actions: { gap: spacing.md, marginTop: spacing.lg },
  primaryAction: { marginBottom: spacing.xs },
  history: { marginTop: spacing.xl, gap: spacing.sm },
  sectionTitle: { ...typography.label, color: colors.textMuted },
  historyItem: { paddingVertical: spacing.md, gap: 2 },
  historyTitle: { ...typography.body, color: colors.text, fontWeight: "600" },
  muted: { ...typography.caption, color: colors.textMuted },
  footer: { marginTop: spacing.xxl, ...typography.caption, color: colors.textMuted },
});
