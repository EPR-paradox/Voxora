import { useQuery } from "@tanstack/react-query";
import { StyleSheet, Text } from "react-native";

import { AppButton } from "../src/components/AppButton";
import { Card } from "../src/components/Card";
import { Screen } from "../src/components/Screen";
import { API_BASE_URL, apiRequest } from "../src/api/client";
import { describeError } from "../src/api/errors";
import { colors, spacing, typography } from "../src/theme";

interface HealthResponse {
  status: string;
  database: string;
  version: string;
}

export default function SettingsScreen() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => apiRequest<HealthResponse>("/health"),
  });

  return (
    <Screen>
      <Card title="后端">
        <Text style={styles.body}>{API_BASE_URL}</Text>
        <Text style={styles.muted}>
          {health.isPending
            ? "检查中…"
            : health.isError
              ? describeError(health.error)
              : health.data
                ? `运行中 · 数据库 ${health.data.database} · 版本 ${health.data.version}`
                : ""}
        </Text>
        <AppButton
          label="重新检查"
          variant="secondary"
          busy={health.isFetching}
          onPress={() => void health.refetch()}
          style={styles.action}
        />
      </Card>

      <Card
        title="数据在哪"
        subtitle="练习记录、反馈、复习项全部在服务端，客户端不留业务数据，换设备或重装都不会丢东西。"
      >
        <Text style={styles.muted}>
          要改后端地址，编辑 apps/mobile/.env.local 里的 EXPO_PUBLIC_API_BASE_URL 再重启 dev server。
        </Text>
      </Card>

      <Card title="这是什么">
        <Text style={styles.body}>
          练英语沟通，不练技术结论。每个场景里 AI 扮演工作里的对话对象，你回答问题；结束后只针对
          表达（清晰度、流畅度、自然度、职场语气、是否答到点上）给反馈，并引用你说过的原话。
        </Text>
      </Card>
    </Screen>
  );
}

const styles = StyleSheet.create({
  body: { ...typography.body, color: colors.text, lineHeight: 22 },
  muted: { ...typography.caption, color: colors.textMuted, lineHeight: 18 },
  action: { marginTop: spacing.sm },
});
