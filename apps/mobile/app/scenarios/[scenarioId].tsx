import { useMutation, useQuery } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { StyleSheet, Text, View } from "react-native";

import { AppButton } from "../../src/components/AppButton";
import { Badge, Card } from "../../src/components/Card";
import { Screen } from "../../src/components/Screen";
import { ErrorView, LoadingView } from "../../src/components/StateViews";
import { describeError } from "../../src/api/errors";
import { createSession } from "../../src/features/practice/api";
import { getScenario } from "../../src/features/scenarios/api";
import { categoryLabels, colors, spacing, speakerColor, typography } from "../../src/theme";

export default function ScenarioDetailScreen() {
  const { scenarioId } = useLocalSearchParams<{ scenarioId: string }>();
  const router = useRouter();

  const query = useQuery({
    queryKey: ["scenario", scenarioId],
    queryFn: () => getScenario(scenarioId),
    enabled: Boolean(scenarioId),
  });

  const start = useMutation({
    mutationFn: () => createSession(scenarioId),
    onSuccess: (session) => {
      // replace, not push: coming back to this screen after finishing would offer a second "start".
      // `speakOpening` tells the practice screen that its first data pass is the greeting, not history.
      router.replace({
        pathname: "/practice/[sessionId]",
        params: { sessionId: session.id, speakOpening: "1" },
      });
    },
  });

  if (query.isPending) {
    return (
      <Screen>
        <LoadingView label="正在取场景…" />
      </Screen>
    );
  }
  if (query.isError || !query.data) {
    return (
      <Screen>
        <ErrorView error={query.error} onRetry={() => void query.refetch()} />
      </Screen>
    );
  }

  const scenario = query.data;
  const character = scenario.ai_character;

  return (
    <Screen>
      <Text style={styles.title}>{scenario.title}</Text>
      <Text style={styles.summary}>{scenario.summary}</Text>

      <View style={styles.badges}>
        <Badge
          label={categoryLabels[scenario.category] ?? scenario.category}
          color={colors.accent}
        />
        <Badge label={`约 ${scenario.estimated_minutes} 分钟`} color={colors.textMuted} />
        <Badge label={`难度 ${scenario.difficulty}/5`} color={colors.textMuted} />
      </View>

      <Card title="场景">
        <Text style={styles.body}>{scenario.situation}</Text>
      </Card>

      {scenario.cast && scenario.cast.length > 1 ? (
        <Card title="这场会议有谁">
          {scenario.cast.map((participant) => (
            <View key={participant.key} style={styles.participantRow}>
              <View
                style={[styles.participantDot, { backgroundColor: speakerColor(participant.key) }]}
              />
              <Text style={styles.participantText}>
                {participant.name}
                {participant.title ? ` · ${participant.title}` : ""}
              </Text>
            </View>
          ))}
        </Card>
      ) : null}

      <Card title="对方是谁">
        <Text style={styles.body}>
          {character?.name ?? "面试官"}
          {character?.title ? `，${character.title}` : ""}
        </Text>
        {character?.communication_style ? (
          <Text style={styles.muted}>{character.communication_style}</Text>
        ) : null}
      </Card>

      <Card title="你要完成的事">
        <Text style={styles.body}>{scenario.user_objective}</Text>
      </Card>

      {scenario.target_expressions.length > 0 ? (
        <Card title="这个场景里值得留意的表达">
          {scenario.target_expressions.map((item, index) => (
            <View key={`${item.expression ?? index}`} style={styles.expression}>
              <Text style={styles.expressionText}>{item.expression}</Text>
              {item.meaning ? <Text style={styles.muted}>{item.meaning}</Text> : null}
            </View>
          ))}
        </Card>
      ) : null}

      {start.isError ? <Text style={styles.error}>{describeError(start.error)}</Text> : null}

      <AppButton
        label={start.isPending ? "正在准备开场…" : "开始练习"}
        busy={start.isPending}
        onPress={() => start.mutate()}
        style={styles.start}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  participantRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  participantDot: { width: 8, height: 8, borderRadius: 4 },
  participantText: { ...typography.body, color: colors.text },
  title: { ...typography.title, color: colors.text },
  summary: { ...typography.body, color: colors.textMuted, marginTop: spacing.sm, lineHeight: 22 },
  badges: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginVertical: spacing.lg },
  body: { ...typography.body, color: colors.text, lineHeight: 22 },
  muted: { ...typography.caption, color: colors.textMuted, lineHeight: 18 },
  expression: { gap: 2, marginBottom: spacing.sm },
  expressionText: { ...typography.body, color: colors.accent },
  error: { color: colors.danger, marginTop: spacing.lg, ...typography.body },
  start: { marginTop: spacing.lg },
});
