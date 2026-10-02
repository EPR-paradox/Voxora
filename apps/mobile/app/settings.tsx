import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { AppButton } from "../src/components/AppButton";
import { Card } from "../src/components/Card";
import { Screen } from "../src/components/Screen";
import { API_BASE_URL, apiRequest } from "../src/api/client";
import { describeError } from "../src/api/errors";
import { clearLastSessionId, getLastSessionId } from "../src/storage";
import { colors, spacing, typography } from "../src/theme";

interface HealthResponse {
  status: string;
  database: string;
  version: string;
}

export default function SettingsScreen() {
  const [cleared, setCleared] = useState<string | null>(null);
  const [lastSessionId, setLastSession] = useState<string | null>(null);

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
        title="本地缓存"
        subtitle="只存「上次练到哪」这一个指针。练习记录和反馈都在服务端，清掉不会丢。"
      >
        <View style={styles.actions}>
          <AppButton
            label="看看存的指针"
            variant="secondary"
            onPress={() => void getLastSessionId().then(setLastSession)}
            style={styles.action}
          />
          <AppButton
            label="清掉"
            variant="secondary"
            onPress={() => {
              void clearLastSessionId();
              setLastSession(null);
              setCleared("已清空本地指针。");
            }}
            style={styles.action}
          />
        </View>
        {lastSessionId ? <Text style={styles.muted}>当前指针：{lastSessionId}</Text> : null}
        {cleared ? <Text style={styles.muted}>{cleared}</Text> : null}
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
  actions: { gap: spacing.sm },
});
