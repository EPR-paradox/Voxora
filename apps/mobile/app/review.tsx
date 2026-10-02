import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { AppButton } from "../src/components/AppButton";
import { Badge, Card } from "../src/components/Card";
import { Screen } from "../src/components/Screen";
import { EmptyState, ErrorView, LoadingView } from "../src/components/StateViews";
import type { ReviewItem, ReviewItemStatus } from "../src/api/types";
import { listReviewItems, nextDueDate, updateReviewItem } from "../src/features/review/api";
import {
  colors,
  radius,
  reviewItemTypeLabels,
  reviewStatusLabels,
  spacing,
  typography,
} from "../src/theme";

const MASTERY_THRESHOLD = 3;

const FILTERS: Array<{ key: ReviewItemStatus | "all"; label: string }> = [
  { key: "new", label: "待复习" },
  { key: "reviewing", label: "复习中" },
  { key: "mastered", label: "已掌握" },
  { key: "all", label: "全部" },
];

export default function ReviewScreen() {
  const [status, setStatus] = useState<ReviewItemStatus | "all">("new");
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ["review-items", status],
    queryFn: () => listReviewItems({ status: status === "all" ? null : status }),
  });

  const grade = useMutation({
    mutationFn: ({ item, remembered }: { item: ReviewItem; remembered: boolean }) =>
      remembered
        ? updateReviewItem(item.id, {
            success_count: item.success_count + 1,
            status: item.success_count + 1 >= MASTERY_THRESHOLD ? "mastered" : "reviewing",
            due_at: nextDueDate(item.success_count + 1),
          })
        : updateReviewItem(item.id, {
            failure_count: item.failure_count + 1,
            status: "reviewing",
            due_at: nextDueDate(0),
          }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["review-items"] });
    },
  });

  return (
    <Screen>
      <View style={styles.filters}>
        {FILTERS.map((filter) => {
          const active = filter.key === status;
          return (
            <Pressable
              key={filter.key}
              onPress={() => setStatus(filter.key)}
              style={[styles.chip, active && styles.chipActive]}
            >
              <Text style={[styles.chipLabel, active && styles.chipLabelActive]}>
                {filter.label}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {query.isPending ? <LoadingView label="正在取复习列表…" /> : null}
      {query.isError ? <ErrorView error={query.error} onRetry={() => void query.refetch()} /> : null}
      {query.data && query.data.items.length === 0 ? (
        <EmptyState
          title="这里还是空的"
          hint="在反馈页把想改的表达加进来，它们会出现在待复习里。"
        />
      ) : null}

      <View style={styles.list}>
        {query.data?.items.map((item) => (
          <Card key={item.id} style={styles.item}>
            {item.original_text ? (
              <Text style={styles.original}>{item.original_text}</Text>
            ) : null}
            <Text style={styles.target}>{item.target_text}</Text>
            {item.explanation ? <Text style={styles.muted}>{item.explanation}</Text> : null}

            <View style={styles.metaRow}>
              <Badge
                label={reviewItemTypeLabels[item.item_type] ?? item.item_type}
                color={colors.accent}
              />
              <Badge
                label={reviewStatusLabels[item.status] ?? item.status}
                color={item.status === "mastered" ? colors.success : colors.textMuted}
              />
              <Text style={styles.muted}>
                记住 {item.success_count} · 忘了 {item.failure_count}
                {item.due_at ? ` · ${formatDue(item.due_at)}` : ""}
              </Text>
            </View>

            <View style={styles.actions}>
              <AppButton
                label="记住了"
                variant="secondary"
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
          </Card>
        ))}
      </View>

      {query.data ? (
        <Text style={styles.total}>共 {query.data.total} 条</Text>
      ) : null}
    </Screen>
  );
}

function formatDue(iso: string): string {
  const due = new Date(iso);
  const now = new Date();
  const days = Math.round((due.getTime() - now.getTime()) / 86_400_000);
  if (days <= 0) return "今天到期";
  if (days === 1) return "明天到期";
  return `${days} 天后`;
}

const styles = StyleSheet.create({
  filters: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  chipActive: { backgroundColor: colors.accent, borderColor: colors.accent },
  chipLabel: { ...typography.caption, color: colors.textMuted },
  chipLabelActive: { color: colors.text },
  list: { gap: spacing.md, marginTop: spacing.lg },
  item: { gap: spacing.xs },
  original: { ...typography.caption, color: colors.textMuted, textDecorationLine: "line-through" },
  target: { ...typography.body, color: colors.text, fontWeight: "600", lineHeight: 22 },
  muted: { ...typography.caption, color: colors.textMuted, lineHeight: 18 },
  metaRow: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: spacing.sm, marginTop: spacing.xs },
  actions: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm },
  action: { flex: 1, minHeight: 38 },
  total: { marginTop: spacing.lg, ...typography.caption, color: colors.textMuted },
});
