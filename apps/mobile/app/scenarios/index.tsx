import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { Card } from "../../src/components/Card";
import { Screen } from "../../src/components/Screen";
import { EmptyState, ErrorView, LoadingView } from "../../src/components/StateViews";
import type { ScenarioCategory } from "../../src/api/types";
import { listScenarios } from "../../src/features/scenarios/api";
import { categoryLabels, colors, radius, spacing, typography } from "../../src/theme";

const FILTERS: Array<{ key: ScenarioCategory | "all"; label: string }> = [
  { key: "all", label: "全部" },
  { key: "interview", label: "面试" },
  { key: "workplace", label: "职场" },
  { key: "travel", label: "出差" },
  { key: "daily_life", label: "生活" },
];

export default function ScenarioListScreen() {
  const router = useRouter();
  const [category, setCategory] = useState<ScenarioCategory | "all">("all");

  const query = useQuery({
    queryKey: ["scenarios", category],
    queryFn: () =>
      listScenarios({ category: category === "all" ? null : category, limit: 50 }),
  });

  return (
    <Screen>
      <View style={styles.filters}>
        {FILTERS.map((filter) => {
          const active = filter.key === category;
          return (
            <Pressable
              key={filter.key}
              onPress={() => setCategory(filter.key)}
              style={[styles.chip, active && styles.chipActive]}
            >
              <Text style={[styles.chipLabel, active && styles.chipLabelActive]}>
                {filter.label}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {query.isPending ? <LoadingView label="正在取场景…" /> : null}
      {query.isError ? <ErrorView error={query.error} onRetry={() => void query.refetch()} /> : null}
      {query.data && query.data.items.length === 0 ? (
        <EmptyState title="这个分类下还没有场景" hint="换个分类看看，或者去后端 seed 更多场景。" />
      ) : null}

      <View style={styles.list}>
        {query.data?.items.map((scenario) => (
          <Pressable
            key={scenario.id}
            onPress={() =>
              router.push({
                pathname: "/scenarios/[scenarioId]",
                params: { scenarioId: scenario.id },
              })
            }
          >
            <Card
              title={scenario.title}
              subtitle={scenario.summary}
              style={styles.item}
            >
              <View style={styles.metaRow}>
                <Text style={styles.meta}>
                  {categoryLabels[scenario.category] ?? scenario.category} · 约{" "}
                  {scenario.estimated_minutes} 分钟 · 难度 {scenario.difficulty}/5
                </Text>
              </View>
              {scenario.target_skills.length > 0 ? (
                <Text style={styles.skills}>{scenario.target_skills.join(" · ")}</Text>
              ) : null}
            </Card>
          </Pressable>
        ))}
      </View>

      {query.data ? (
        <Text style={styles.total}>共 {query.data.total} 个场景</Text>
      ) : null}
    </Screen>
  );
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
  metaRow: { flexDirection: "row", flexWrap: "wrap" },
  meta: { ...typography.caption, color: colors.textMuted },
  skills: { ...typography.caption, color: colors.accent },
  total: { marginTop: spacing.lg, ...typography.caption, color: colors.textMuted },
});
