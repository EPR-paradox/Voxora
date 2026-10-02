import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { StyleSheet, Text, View } from "react-native";

import { AppButton } from "../../src/components/AppButton";
import { Badge, Card } from "../../src/components/Card";
import { Screen } from "../../src/components/Screen";
import { ErrorView, LoadingView } from "../../src/components/StateViews";
import { describeError } from "../../src/api/errors";
import type { ReviewItem } from "../../src/api/types";
import { getReviewItem, gradeReviewItemInput, updateReviewItem } from "../../src/features/review/api";
import { formatDateTime, formatDue } from "../../src/features/review/format";
import {
  colors,
  reviewItemTypeLabels,
  reviewStatusLabels,
  spacing,
  typography,
} from "../../src/theme";

/**
 * One review item, in full (design §10.1).
 *
 * The list screen shows an item in one glance, which is the wrong shape for the thing being reviewed:
 * the original sentence and the better version sit side by side, so there is nothing to recall. This
 * screen gives the wording room, keeps the learner's own sentence as the headline instead of a struck
 * through footnote, and links back to the practice that produced it: `source_session_id` was stored from
 * the first version but had nowhere to be seen.
 *
 * The item is fetched by id rather than picked out of the list cache, so a deep link or a reloaded app
 * (no list in memory) still renders.
 */
export default function ReviewItemScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ["review-item", id],
    queryFn: () => getReviewItem(id),
    enabled: Boolean(id),
  });

  const grade = useMutation({
    mutationFn: ({ item, remembered }: { item: ReviewItem; remembered: boolean }) =>
      updateReviewItem(item.id, gradeReviewItemInput(item, remembered)),
    onSuccess: (updated) => {
      queryClient.setQueryData(["review-item", updated.id], updated);
      void queryClient.invalidateQueries({ queryKey: ["review-items"] });
    },
  });

  if (query.isPending) {
    return (
      <Screen>
        <LoadingView label="正在取复习项…" />
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

  const item = query.data;
  const sourceSessionId = item.source_session_id;

  return (
    <Screen>
      <View style={styles.badges}>
        <Badge label={reviewItemTypeLabels[item.item_type] ?? item.item_type} color={colors.accent} />
        <Badge
          label={reviewStatusLabels[item.status] ?? item.status}
          color={item.status === "mastered" ? colors.success : colors.textMuted}
        />
      </View>

      <Card title="你当时说的">
        <Text style={styles.original}>
          {item.original_text ?? "这条没有留下原句，只有推荐表达。"}
        </Text>
      </Card>

      <Card title="更好的说法">
        <Text style={styles.target}>{item.target_text}</Text>
      </Card>

      {item.explanation ? (
        <Card title="为什么">
          <Text style={styles.body}>{item.explanation}</Text>
        </Card>
      ) : null}

      <Card title="复习记录">
        <Text style={styles.muted}>
          记住 {item.success_count} 次 · 忘了 {item.failure_count} 次
        </Text>
        <Text style={styles.muted}>
          下次复习：{item.due_at ? formatDue(item.due_at) : "未排期"}
        </Text>
        <Text style={styles.muted}>加入时间：{formatDateTime(item.created_at)}</Text>
      </Card>

      {sourceSessionId ? (
        <AppButton
          label="看那次练习的反馈"
          variant="secondary"
          onPress={() =>
            router.push({ pathname: "/evaluation/[sessionId]", params: { sessionId: sourceSessionId } })
          }
        />
      ) : null}

      <View style={styles.actions}>
        <AppButton
          label="记住了"
          busy={grade.isPending}
          onPress={() => grade.mutate({ item, remembered: true })}
          style={styles.action}
        />
        <AppButton
          label="还没记住"
          variant="secondary"
          busy={grade.isPending}
          onPress={() => grade.mutate({ item, remembered: false })}
          style={styles.action}
        />
      </View>
      {grade.isError ? <Text style={styles.error}>{describeError(grade.error)}</Text> : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  badges: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginBottom: spacing.md },
  original: { ...typography.body, color: colors.text, lineHeight: 24 },
  target: { ...typography.heading, color: colors.text, lineHeight: 26 },
  body: { ...typography.body, color: colors.text, lineHeight: 22 },
  muted: { ...typography.caption, color: colors.textMuted, lineHeight: 18 },
  actions: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md },
  action: { flex: 1 },
  error: { ...typography.caption, color: colors.danger, marginTop: spacing.sm },
});
