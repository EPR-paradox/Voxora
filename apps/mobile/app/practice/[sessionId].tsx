import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Stack, useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useMemo, useRef, useState } from "react";
import {
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { AppButton } from "../../src/components/AppButton";
import { ErrorView, LoadingView } from "../../src/components/StateViews";
import { newClientMessageId } from "../../src/api/client";
import { ApiError, describeError } from "../../src/api/errors";
import { finishSession } from "../../src/features/evaluation/api";
import { getSession, sendMessage } from "../../src/features/practice/api";
import { colors, radius, spacing, typography } from "../../src/theme";

interface OutboxItem {
  clientMessageId: string;
  content: string;
  failed: boolean;
}

/**
 * The practice conversation (design §10.3).
 *
 * The list is server state; `outbox` holds only the turn that has not been confirmed yet. That split is
 * what makes the retry rule work: a failed turn keeps its text *and* its `client_message_id`, so pressing
 * retry replays the same key and the backend returns the original exchange instead of writing a second
 * user message (§7.6, §9.3).
 */
export default function PracticeScreen() {
  const { sessionId } = useLocalSearchParams<{ sessionId: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const insets = useSafeAreaInsets();
  const listRef = useRef<FlatList>(null);

  const [draft, setDraft] = useState("");
  const [outbox, setOutbox] = useState<OutboxItem[]>([]);

  const sessionQuery = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => getSession(sessionId),
    enabled: Boolean(sessionId),
  });

  const send = useMutation({
    mutationFn: (item: OutboxItem) => sendMessage(sessionId, item.content, item.clientMessageId),
    onSuccess: async (_response, item) => {
      setOutbox((items) => items.filter((entry) => entry.clientMessageId !== item.clientMessageId));
      setDraft("");
      await queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
    },
    onError: (error, item) => {
      if (error instanceof ApiError && error.code === "session_not_active") {
        // Finished elsewhere: the only useful place to be is the report.
        router.replace({ pathname: "/evaluation/[sessionId]", params: { sessionId } });
        return;
      }
      setOutbox((items) =>
        items.map((entry) =>
          entry.clientMessageId === item.clientMessageId ? { ...entry, failed: true } : entry,
        ),
      );
    },
  });

  const finish = useMutation({
    mutationFn: () => finishSession(sessionId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
      router.replace({ pathname: "/evaluation/[sessionId]", params: { sessionId } });
    },
  });

  const submit = useCallback(() => {
    const content = draft.trim();
    if (!content || send.isPending) return;
    const item: OutboxItem = { clientMessageId: newClientMessageId(), content, failed: false };
    setOutbox((items) => [...items, item]);
    setDraft("");
    send.mutate(item);
  }, [draft, send]);

  const retry = useCallback(
    (item: OutboxItem) => {
      setOutbox((items) =>
        items.map((entry) =>
          entry.clientMessageId === item.clientMessageId ? { ...entry, failed: false } : entry,
        ),
      );
      send.mutate({ ...item, failed: false });
    },
    [send],
  );

  const messages = sessionQuery.data?.messages ?? [];
  const session = sessionQuery.data;

  const rows = useMemo(
    () => [
      ...messages.map((message) => ({
        key: message.id,
        role: message.role,
        content: message.content,
        pending: message.status === "pending",
        failed: message.status === "failed",
        local: false,
      })),
      ...outbox.map((item) => ({
        key: item.clientMessageId,
        role: "user" as const,
        content: item.content,
        pending: !item.failed,
        failed: item.failed,
        local: true,
      })),
    ],
    [messages, outbox],
  );

  if (sessionQuery.isPending) {
    return (
      <View style={styles.root}>
        <LoadingView label="正在恢复练习…" />
      </View>
    );
  }
  if (sessionQuery.isError || !session) {
    return (
      <View style={styles.root}>
        <ErrorView error={sessionQuery.error} onRetry={() => void sessionQuery.refetch()} />
      </View>
    );
  }

  const canFinish = session.turn_count > 0 && !finish.isPending;
  const finished = session.status !== "active";

  return (
    <View style={styles.root}>
      <Stack.Screen
        options={{
          title: session.scenario.title,
          headerRight: () =>
            finished ? null : (
              <Pressable
                disabled={!canFinish}
                onPress={() => finish.mutate()}
                style={({ pressed }) => [pressed && styles.pressed]}
              >
                <Text style={[styles.headerAction, !canFinish && styles.headerActionDisabled]}>
                  {finish.isPending ? "生成中…" : "结束"}
                </Text>
              </Pressable>
            ),
        }}
      />

      <FlatList
        ref={listRef}
        data={rows}
        keyExtractor={(row) => row.key}
        contentContainerStyle={styles.listContent}
        onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: true })}
        renderItem={({ item }) => (
          <View style={[styles.bubble, item.role === "user" ? styles.userBubble : styles.aiBubble]}>
            <Text style={styles.bubbleLabel}>{item.role === "user" ? "你" : session.scenario.title}</Text>
            <Text style={styles.bubbleText}>{item.content}</Text>
            {item.pending ? <Text style={styles.bubbleStatus}>发送中…</Text> : null}
            {item.failed ? (
              <View style={styles.retryRow}>
                <Text style={styles.bubbleStatusError}>没发出去</Text>
                <Pressable onPress={() => retry(outbox.find((entry) => entry.clientMessageId === item.key)!)}>
                  <Text style={styles.retryLabel}>重试</Text>
                </Pressable>
              </View>
            ) : null}
          </View>
        )}
      />

      {send.isError && !outbox.some((item) => item.failed) ? (
        <Text style={styles.error}>{describeError(send.error)}</Text>
      ) : null}

      {finished ? (
        <View style={styles.footerBar}>
          <AppButton
            label="看反馈"
            onPress={() =>
              router.replace({ pathname: "/evaluation/[sessionId]", params: { sessionId } })
            }
          />
        </View>
      ) : (
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined}>
          <View style={[styles.composer, { paddingBottom: insets.bottom + spacing.sm }]}>
            <TextInput
              style={styles.input}
              value={draft}
              onChangeText={setDraft}
              placeholder="用英语回答…"
              placeholderTextColor={colors.textMuted}
              multiline
              editable={!send.isPending}
              onSubmitEditing={submit}
              blurOnSubmit={false}
            />
            <AppButton
              label="发送"
              busy={send.isPending}
              disabled={draft.trim().length === 0}
              onPress={submit}
            />
          </View>
        </KeyboardAvoidingView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.background },
  listContent: { padding: spacing.lg, gap: spacing.md },
  bubble: { borderRadius: radius.lg, padding: spacing.md, gap: spacing.xs, maxWidth: "92%" },
  userBubble: { alignSelf: "flex-end", backgroundColor: colors.accent },
  aiBubble: { alignSelf: "flex-start", backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  bubbleLabel: { ...typography.caption, color: colors.textMuted, opacity: 0.9 },
  bubbleText: { ...typography.body, color: colors.text, lineHeight: 22 },
  bubbleStatus: { ...typography.caption, color: colors.textMuted },
  bubbleStatusError: { ...typography.caption, color: colors.danger },
  retryRow: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  retryLabel: { ...typography.caption, color: colors.text, fontWeight: "700" },
  composer: {
    flexDirection: "row",
    alignItems: "flex-end",
    gap: spacing.sm,
    padding: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.surface,
  },
  input: {
    flex: 1,
    minHeight: 44,
    maxHeight: 140,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceMuted,
    color: colors.text,
    ...typography.body,
  },
  footerBar: { padding: spacing.lg },
  headerAction: { color: colors.accent, fontSize: 15, fontWeight: "600" },
  headerActionDisabled: { color: colors.textMuted },
  pressed: { opacity: 0.7 },
  error: { color: colors.danger, paddingHorizontal: spacing.lg, paddingBottom: spacing.sm, ...typography.caption },
});
