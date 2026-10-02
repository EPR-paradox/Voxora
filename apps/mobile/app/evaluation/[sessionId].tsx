import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { AppButton } from "../../src/components/AppButton";
import { Badge, Card } from "../../src/components/Card";
import { Screen } from "../../src/components/Screen";
import { EmptyState, ErrorView, LoadingView } from "../../src/components/StateViews";
import { ApiError, describeError } from "../../src/api/errors";
import type { EvaluationReviewItem } from "../../src/api/types";
import { finishSession, getEvaluation, retryEvaluation } from "../../src/features/evaluation/api";
import { getSession } from "../../src/features/practice/api";
import { createReviewItem } from "../../src/features/review/api";
import {
  colors,
  dimensionLabels,
  errorCodeLabels,
  ratingColors,
  ratingLabels,
  radius,
  reviewItemTypeLabels,
  spacing,
  typography,
} from "../../src/theme";

export default function EvaluationScreen() {
  const { sessionId } = useLocalSearchParams<{ sessionId: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [addedItems, setAddedItems] = useState<Record<string, boolean>>({});

  const sessionQuery = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => getSession(sessionId),
    enabled: Boolean(sessionId),
  });

  const evaluationQuery = useQuery({
    queryKey: ["evaluation", sessionId],
    queryFn: () => getEvaluation(sessionId),
    enabled: Boolean(sessionId),
    // A missing evaluation is a normal state here (the learner may open this screen first), so it must
    // not be retried; a report that is still processing must be polled instead.
    retry: (failureCount, error) =>
      !(error instanceof ApiError && error.code === "evaluation_not_found") && failureCount < 1,
    refetchInterval: (query) => {
      const status = query.state.data?.evaluation_status;
      return status === "pending" || status === "processing" ? 3000 : false;
    },
  });

  const finish = useMutation({
    mutationFn: () => finishSession(sessionId),
    onSuccess: async (payload) => {
      queryClient.setQueryData(["evaluation", sessionId], payload);
      await queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
    },
  });

  const retry = useMutation({
    mutationFn: () => retryEvaluation(sessionId),
    onSuccess: (payload) => queryClient.setQueryData(["evaluation", sessionId], payload),
  });

  const addToReview = useMutation({
    mutationFn: (item: EvaluationReviewItem) =>
      createReviewItem({
        source_session_id: sessionId,
        item_type: (item.item_type as "expression") ?? "expression",
        original_text: item.original_text,
        target_text: item.target_text,
        explanation: item.explanation,
      }),
    onSuccess: (_created, item) => {
      setAddedItems((current) => ({ ...current, [item.target_text]: true }));
      void queryClient.invalidateQueries({ queryKey: ["review-items"] });
    },
  });

  if (sessionQuery.isPending || evaluationQuery.isPending) {
    return (
      <Screen>
        <LoadingView label="正在取反馈…" />
      </Screen>
    );
  }

  if (sessionQuery.isError || !sessionQuery.data) {
    return (
      <Screen>
        <ErrorView error={sessionQuery.error} onRetry={() => void sessionQuery.refetch()} />
      </Screen>
    );
  }

  const session = sessionQuery.data;
  const evaluation = evaluationQuery.data;
  const missingEvaluation =
    evaluationQuery.isError &&
    evaluationQuery.error instanceof ApiError &&
    evaluationQuery.error.code === "evaluation_not_found";

  if (session.status === "active") {
    return (
      <Screen>
        <EmptyState
          title="这次练习还没结束"
          hint="回对话里再聊几句，然后点右上角「结束」；或者在这里直接结束并生成反馈。"
        />
        {finish.isError ? <Text style={styles.error}>{describeError(finish.error)}</Text> : null}
        <AppButton
          label={finish.isPending ? "正在生成反馈，约 15 秒…" : "结束练习并生成反馈"}
          busy={finish.isPending}
          disabled={session.turn_count === 0}
          onPress={() => finish.mutate()}
          style={styles.action}
        />
        {session.turn_count === 0 ? (
          <Text style={styles.hint}>至少说一句才能评价。</Text>
        ) : null}
        <AppButton
          label="回到对话"
          variant="secondary"
          onPress={() => router.replace({ pathname: "/practice/[sessionId]", params: { sessionId } })}
          style={styles.action}
        />
      </Screen>
    );
  }

  if (missingEvaluation) {
    return (
      <Screen>
        <EmptyState title="这次练习还没有反馈" hint="结束练习后就会生成。" />
        <AppButton
          label={finish.isPending ? "正在生成反馈，约 15 秒…" : "生成反馈"}
          busy={finish.isPending}
          onPress={() => finish.mutate()}
          style={styles.action}
        />
      </Screen>
    );
  }

  if (evaluationQuery.isError || !evaluation) {
    return (
      <Screen>
        <ErrorView error={evaluationQuery.error} onRetry={() => void evaluationQuery.refetch()} />
      </Screen>
    );
  }

  const status = evaluation.evaluation_status;

  if (status === "pending" || status === "processing") {
    return (
      <Screen>
        <LoadingView label="正在生成反馈，通常 15 秒左右…" />
      </Screen>
    );
  }

  if (status === "failed" || !evaluation.evaluation) {
    return (
      <Screen>
        <Card
          title="反馈没生成出来"
          subtitle={
            errorCodeLabels[evaluation.error_code ?? ""] ??
            "模型这次没给出可用的反馈，重试一次通常就好。"
          }
        >
          <Text style={styles.muted}>
            已尝试 {evaluation.attempt_count} 次。你的对话记录都还在，重试不会重新练习。
          </Text>
        </Card>
        <AppButton
          label={retry.isPending ? "重新生成中…" : "重试生成反馈"}
          busy={retry.isPending}
          onPress={() => retry.mutate()}
          style={styles.action}
        />
        {retry.isError ? <Text style={styles.error}>{describeError(retry.error)}</Text> : null}
      </Screen>
    );
  }

  const report = evaluation.evaluation;

  return (
    <Screen>
      <Card title="总评">
        <Text style={styles.body}>{report.summary}</Text>
      </Card>

      {Object.entries(report.dimensions).map(([key, dimension]) =>
        dimension ? (
          <Card key={key} title={dimensionLabels[key] ?? key}>
            <View style={styles.ratingRow}>
              <Badge
                label={ratingLabels[dimension.rating] ?? dimension.rating}
                color={ratingColors[dimension.rating] ?? colors.textMuted}
              />
            </View>
            <Text style={styles.body}>{dimension.feedback}</Text>
            {dimension.evidence.map((quote) => (
              <Text key={quote} style={styles.quote}>
                「{quote}」
              </Text>
            ))}
          </Card>
        ) : null,
      )}

      {report.strengths.length > 0 ? (
        <Card title="做得好的地方">
          {report.strengths.map((item) => (
            <Text key={item} style={styles.bullet}>
              · {item}
            </Text>
          ))}
        </Card>
      ) : null}

      {report.improvements.length > 0 ? (
        <Card title="改进点">
          {report.improvements.map((item) => (
            <Text key={item} style={styles.bullet}>
              · {item}
            </Text>
          ))}
        </Card>
      ) : null}

      {report.suggested_rephrases.length > 0 ? (
        <Card title="可以这样说">
          {report.suggested_rephrases.map((item) => (
            <View key={item.suggestion} style={styles.rephrase}>
              <Text style={styles.original}>{item.original}</Text>
              <Text style={styles.suggestion}>{item.suggestion}</Text>
              {item.reason ? <Text style={styles.muted}>{item.reason}</Text> : null}
            </View>
          ))}
        </Card>
      ) : null}

      {report.review_items.length > 0 ? (
        <Card title="加进复习列表" subtitle="挑你真正想改的，不用全收。">
          {report.review_items.map((item) => {
            const added = addedItems[item.target_text];
            return (
              <View key={`${item.item_type}-${item.target_text}`} style={styles.reviewRow}>
                <View style={styles.reviewText}>
                  <Text style={styles.original}>{item.original_text}</Text>
                  <Text style={styles.suggestion}>{item.target_text}</Text>
                  <Text style={styles.muted}>
                    {reviewItemTypeLabels[item.item_type] ?? item.item_type}
                    {item.explanation ? ` · ${item.explanation}` : ""}
                  </Text>
                </View>
                <AppButton
                  label={added ? "已加入" : "加入"}
                  variant="secondary"
                  disabled={added || addToReview.isPending}
                  onPress={() => addToReview.mutate(item)}
                  style={styles.addButton}
                />
              </View>
            );
          })}
        </Card>
      ) : null}

      <AppButton
        label="去复习列表"
        variant="secondary"
        onPress={() => router.push("/review")}
        style={styles.action}
      />
      <Text style={styles.footnote}>
        评分标准 {report.rubric_version} · 第 {evaluation.attempt_count} 次生成
      </Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  body: { ...typography.body, color: colors.text, lineHeight: 22 },
  muted: { ...typography.caption, color: colors.textMuted, lineHeight: 18 },
  quote: { ...typography.body, color: colors.accent, fontStyle: "italic", lineHeight: 21 },
  bullet: { ...typography.body, color: colors.text, lineHeight: 22 },
  ratingRow: { flexDirection: "row", gap: spacing.sm },
  rephrase: { gap: spacing.xs, marginBottom: spacing.md },
  original: { ...typography.body, color: colors.textMuted, textDecorationLine: "line-through" },
  suggestion: { ...typography.body, color: colors.text, fontWeight: "600", lineHeight: 22 },
  reviewRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  reviewText: { flex: 1, gap: 2 },
  addButton: { minHeight: 36, paddingHorizontal: spacing.md, borderRadius: radius.md },
  action: { marginTop: spacing.lg },
  footnote: { marginTop: spacing.lg, ...typography.caption, color: colors.textMuted },
  hint: { ...typography.caption, color: colors.textMuted, marginTop: spacing.sm },
  error: { color: colors.danger, marginTop: spacing.md, ...typography.body },
});
