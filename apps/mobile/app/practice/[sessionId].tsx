import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Stack, useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import type { PracticeSessionDetail } from "../../src/api/types";
import { finishSession } from "../../src/features/evaluation/api";
import { abandonSession, getSession, sendMessage } from "../../src/features/practice/api";
import { mergeExchange, messageKey } from "../../src/features/practice/messages";
import { useMeetingListening } from "../../src/features/practice/useMeetingListening";
import { useSpeechOutput, type SpeechLine } from "../../src/features/speech/useSpeechOutput";
import { formatDuration, useVoiceInput } from "../../src/features/speech/useVoiceInput";
import { colors, radius, spacing, speakerColor, typography } from "../../src/theme";

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
  // `speakOpening` marks the one entry where the lines that arrive are not history: the session was created
  // a moment ago by 开始练习, so what lands on the first pass is the greeting itself.
  const { sessionId, speakOpening } = useLocalSearchParams<{
    sessionId: string;
    speakOpening?: string;
  }>();
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
    onSuccess: (response, item) => {
      // Fold the exchange into the cache *first*, then drop the optimistic row: React batches both into one
      // render, so the message goes straight from the local row to the server row with the same key
      // (`messageKey`) and is never missing from the list. Invalidate afterwards to reconcile whatever the
      // response does not carry — that refetch can no longer open a hole, because the data is already there.
      queryClient.setQueryData<PracticeSessionDetail>(["session", sessionId], (current) =>
        current ? mergeExchange(current, response) : current,
      );
      setOutbox((items) => items.filter((entry) => entry.clientMessageId !== item.clientMessageId));
      setDraft("");
      void queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
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

  // Listening-only sessions have no report to fetch, so they end here instead (§7.15). Without this the
  // session could be opened and never closed: `finish` refuses when the learner never spoke.
  const abandon = useMutation({
    mutationFn: () => abandonSession(sessionId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
      router.replace("/");
    },
  });

  const submit = useCallback(() => {
    const content = draft.trim();
    if (!content || send.isPending) return;
    const item: OutboxItem = { clientMessageId: newClientMessageId(), content, failed: false };
    stopListeningRef.current();
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
  const participants = useMemo(() => session?.participants ?? [], [session]);
  // Meeting mode: more than one participant in the room (§7.7). Read here because the voice callback
  // below needs it, and the screens' early returns come later.
  const inMeeting = (session?.participants.length ?? 0) > 1;

  // A meeting puts several participants in one turn, so every row carries who said it and whether it
  // starts a new speaker run. Consecutive lines from one person are drawn as a group; otherwise three
  // voices in a row look like one long wall of text.
  const rows = useMemo(() => {
    // A turn whose server row has already arrived is rendered from the cache, never twice: the local row is
    // the same turn, and for one render after a refetch both exist.
    const localKeys = new Set(outbox.map((item) => item.clientMessageId));
    const serverRows = messages
      .filter((message) => !message.client_message_id || !localKeys.has(message.client_message_id))
      .map((message) => ({
        key: messageKey(message),
        role: message.role,
        speakerKey: message.speaker_key,
        speakerName: message.speaker?.name ?? null,
        content: message.content,
        pending: message.status === "pending",
        failed: message.status === "failed",
        local: false,
      }));
    const localRows = outbox.map((item) => ({
      key: item.clientMessageId,
      role: "user" as const,
      speakerKey: "",
      speakerName: null,
      content: item.content,
      pending: !item.failed,
      failed: item.failed,
      local: true,
    }));
    const all = [...serverRows, ...localRows];
    return all.map((row, index) => ({
      ...row,
      startsSpeaker: index === 0 || all[index - 1].speakerKey !== row.speakerKey,
    }));
  }, [messages, outbox]);

  // Voice input (design §10.4). What the finished text does depends on the room: a meeting sends it
  // straight away, a single-character practice drops it into the box so a mis-heard word can be fixed
  // before it becomes learner history.
  const voice = useVoiceInput(
    useCallback(
      (text: string) => {
        const spoken = text.trim();
        if (!spoken || send.isPending) return;
        if (inMeeting) {
          const item: OutboxItem = { clientMessageId: newClientMessageId(), content: spoken, failed: false };
          setOutbox((items) => [...items, item]);
          send.mutate(item);
          return;
        }
        setDraft((current) => (current ? `${current} ${spoken}` : spoken));
      },
      [inMeeting, send],
    ),
  );

  // Voice output (meeting-mode §9). Every participant speaks with the voice the server picked for them,
  // so the client never keeps its own copy of the catalog.
  const speech = useSpeechOutput();

  // Listening without speaking (design §7.14). The cursor is the last seq the screen has seen: it is what
  // makes a retried advance free, and it has to be read at call time, never captured.
  const cursorRef = useRef(0);
  useEffect(() => {
    cursorRef.current = messages.reduce(
      (highest, message) => Math.max(highest, message.seq),
      cursorRef.current,
    );
  }, [messages]);
  const speechBusyRef = useRef(speech.busy);
  speechBusyRef.current = speech.busy;
  const listening = useMeetingListening({
    sessionId,
    getCursor: () => cursorRef.current,
    enabled: inMeeting && session?.status === "active",
    isSpeaking: () => speechBusyRef.current,
  });
  const voiceByKey = useMemo(() => {
    const map = new Map<string, string | null>();
    for (const participant of participants) map.set(participant.key, participant.voice ?? null);
    return map;
  }, [participants]);

  const asSpeechLine = useCallback(
    (message: { id: string; speaker_key: string; content: string }): SpeechLine => ({
      id: message.id,
      text: message.content,
      voice: voiceByKey.get(message.speaker_key) ?? null,
    }),
    [voiceByKey],
  );

  // Speak the AI's lines as they arrive — but never the backlog. Entering a session with ten turns of
  // history must not start a monologue; the first pass only marks what is already there as heard.
  //
  // "First pass" has to mean the first pass *with data*. The screen renders once while the session query is
  // still pending, and seeding on that empty snapshot marks nothing: the transcript then arrives looking
  // entirely new, and opening a past session reads it out from the first line (measured: one synthesize
  // request per assistant turn, one per second, just from opening the page).
  //
  // The one entry where those first lines are not history is a session created a moment ago by 开始练习
  // (`speakOpening`): the greeting is the current turn, not a backlog.
  const spokenRef = useRef<Set<string>>(new Set());
  const seededRef = useRef(false);
  useEffect(() => {
    if (messages.length === 0) return;
    const assistant = messages.filter((message) => message.role === "assistant");
    if (!seededRef.current) {
      seededRef.current = true;
      if (speakOpening !== "1") {
        for (const message of assistant) spokenRef.current.add(message.id);
        return;
      }
    }
    const fresh = assistant.filter((message) => !spokenRef.current.has(message.id));
    if (fresh.length === 0) return;
    for (const message of fresh) spokenRef.current.add(message.id);
    speech.speak(fresh.map(asSpeechLine));
  }, [asSpeechLine, messages, speech]);

  // Taking the floor ends both: the speaker goes silent (otherwise the learner records the AI's voice into
  // their turn, §9.2) and the meeting stops advancing on its own (§7.14) — listening is over the moment
  // they speak.
  const stopSpeechRef = useRef(speech.stop);
  stopSpeechRef.current = speech.stop;
  const stopListeningRef = useRef(listening.stop);
  stopListeningRef.current = listening.stop;
  useEffect(() => {
    if (voice.phase !== "idle") {
      stopSpeechRef.current();
      stopListeningRef.current();
    }
  }, [voice.phase]);

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

  const hasSpoken = session.turn_count > 0;
  const ending = finish.isPending || abandon.isPending;
  const canEnd = !ending;
  const finished = session.status !== "active";

  return (
    <View style={styles.root}>
      <Stack.Screen
        options={{
          title: session.scenario.title,
          headerRight: () => (
            <View style={styles.headerActions}>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={speech.muted ? "打开语音播放" : "静音"}
                onPress={() => speech.setMuted(!speech.muted)}
                style={({ pressed }) => [pressed && styles.pressed]}
              >
                <Text style={[styles.headerAction, speech.muted && styles.headerActionDisabled]}>
                  {speech.muted ? "静音" : "有声"}
                </Text>
              </Pressable>
              {finished ? null : (
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={hasSpoken ? "结束并生成评价" : "结束这次旁听"}
                  disabled={!canEnd}
                  onPress={() => {
                    // Speaking ends listening, and so does leaving: stop the room before closing it.
                    stopListeningRef.current();
                    stopSpeechRef.current();
                    if (hasSpoken) finish.mutate();
                    else abandon.mutate();
                  }}
                  style={({ pressed }) => [pressed && styles.pressed]}
                >
                  <Text style={[styles.headerAction, !canEnd && styles.headerActionDisabled]}>
                    {ending ? "处理中…" : "结束"}
                  </Text>
                </Pressable>
              )}
            </View>
          ),
        }}
      />

      {session.participants.length > 1 ? (
        <View style={styles.participants}>
          {session.participants.map((participant) => (
            <View key={participant.key} style={styles.participant}>
              <View
                style={[styles.participantDot, { backgroundColor: speakerColor(participant.key) }]}
              />
              <Text style={styles.participantName}>{participant.name}</Text>
            </View>
          ))}
        </View>
      ) : null}

      {inMeeting && !finished ? (
        <View style={styles.listenBar}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={listening.listening ? "停止旁听" : "开始旁听"}
            onPress={listening.toggle}
            style={({ pressed }) => [
              styles.listenButton,
              listening.listening && styles.listenButtonActive,
              pressed && styles.pressed,
            ]}
          >
            <Text style={[styles.listenLabel, listening.listening && styles.listenLabelActive]}>
              {listening.listening ? "停止旁听" : "旁听"}
            </Text>
          </Pressable>
          <Text style={styles.listenHint}>
            {listening.listening
              ? listening.advancesRemaining === null
                ? "只听不说，会议自己进行…"
                : `只听不说 · 还能推进 ${listening.advancesRemaining} 次`
              : hasSpoken
                ? "点「旁听」让会议自己进行，你只听；随时可以开口"
                : "点「旁听」让会议自己进行。你还没发言，结束时不会生成评价"}
          </Text>
        </View>
      ) : null}

      <FlatList
        ref={listRef}
        data={rows}
        keyExtractor={(row) => row.key}
        contentContainerStyle={styles.listContent}
        onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: true })}
        renderItem={({ item }) => (
          <View
            style={[
              styles.bubble,
              item.role === "user" ? styles.userBubble : styles.aiBubble,
              item.role === "assistant" && !item.startsSpeaker ? styles.groupedBubble : null,
              item.role === "assistant" && item.speakerKey
                ? { borderLeftColor: speakerColor(item.speakerKey), borderLeftWidth: 3 }
                : null,
            ]}
          >
            {item.role === "user" ? (
              <Text style={styles.bubbleLabel}>你</Text>
            ) : item.startsSpeaker ? (
              <Text style={styles.bubbleLabel}>{item.speakerName ?? session.scenario.title}</Text>
            ) : null}
            <Text style={styles.bubbleText}>{item.content}</Text>
            {item.role === "assistant" && !item.pending && !item.failed ? (
              <View style={styles.speakRow}>
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={speech.playingId === item.key ? "停止播放" : "朗读这一句"}
                  onPress={() => {
                    if (speech.playingId === item.key) {
                      speech.stop();
                      return;
                    }
                    const message = messages.find((entry) => entry.id === item.key);
                    if (message) speech.replay(asSpeechLine(message));
                  }}
                  style={({ pressed }) => [pressed && styles.pressed]}
                >
                  <Text style={styles.speakLabel}>
                    {speech.playingId === item.key ? "停止" : "朗读"}
                  </Text>
                </Pressable>
              </View>
            ) : null}
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

      {speech.error ? <Text style={styles.error}>朗读失败：{speech.error}</Text> : null}
      {listening.error ? <Text style={styles.error}>{listening.error}</Text> : null}
      {finish.isError ? (
        <Text style={styles.error}>{describeError(finish.error)}</Text>
      ) : null}
      {abandon.isError ? (
        <Text style={styles.error}>{describeError(abandon.error)}</Text>
      ) : null}

      {finished ? (
        <View style={styles.footerBar}>
          {session.status === "abandoned" ? (
            // Listening-only sessions end without a report (§7.15): send them home, not to an empty page.
            <AppButton label="返回" onPress={() => router.replace("/")} />
          ) : (
            <AppButton
              label="看反馈"
              onPress={() =>
                router.replace({ pathname: "/evaluation/[sessionId]", params: { sessionId } })
              }
            />
          )}
        </View>
      ) : (
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined}>
          {voice.phase === "recording" ? (
            <View style={styles.recordingStrip}>
              <View style={styles.recordingDot} />
              <View style={styles.levelTrack}>
                <View style={[styles.levelFill, { width: `${Math.round(voice.level * 100)}%` }]} />
              </View>
              <Text style={[styles.recordingTime, voice.endingSoon && styles.recordingTimeWarn]}>
                {formatDuration(voice.elapsedMs)}
              </Text>
            </View>
          ) : null}

          {voice.phase === "transcribing" ? (
            <View style={styles.voiceStrip}>
              <Text style={styles.voiceStripText}>识别中…</Text>
              <Pressable onPress={voice.cancel}>
                <Text style={styles.linkLabel}>取消</Text>
              </Pressable>
            </View>
          ) : null}

          {voice.error ? (
            <View style={styles.voiceStrip}>
              <Text style={styles.voiceErrorText}>{voice.error}</Text>
              <Pressable onPress={voice.retry}>
                <Text style={styles.linkLabel}>重试同一段</Text>
              </Pressable>
              <Pressable onPress={voice.cancel}>
                <Text style={styles.linkLabel}>重新录</Text>
              </Pressable>
            </View>
          ) : null}

          {voice.permissionDenied ? (
            <Text style={styles.voiceHint}>
              没有麦克风权限。先用打字，需要开麦就去系统设置里允许。
            </Text>
          ) : null}

          <View style={[styles.composer, { paddingBottom: insets.bottom + spacing.sm }]}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={voice.phase === "recording" ? "闭麦并识别" : "开麦"}
              onPress={voice.toggle}
              disabled={send.isPending || voice.phase === "transcribing"}
              style={({ pressed }) => [
                styles.mic,
                voice.phase === "recording" && styles.micActive,
                pressed && styles.pressed,
              ]}
            >
              <Text
                style={[styles.micLabel, voice.phase === "recording" && styles.micLabelActive]}
              >
                {voice.phase === "recording" ? "闭麦" : "开麦"}
              </Text>
            </Pressable>
            <TextInput
              style={styles.input}
              value={draft}
              onChangeText={setDraft}
              placeholder={inMeeting ? "说一句，或直接打字…" : "用英语回答…"}
              placeholderTextColor={colors.textMuted}
              multiline
              editable={!send.isPending && voice.phase === "idle"}
              onSubmitEditing={submit}
              blurOnSubmit={false}
            />
            <AppButton
              label="发送"
              busy={send.isPending}
              disabled={draft.trim().length === 0 || voice.phase !== "idle"}
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
  // Same speaker continuing: tighter, and the name is not repeated.
  groupedBubble: { marginTop: -spacing.sm },
  participants: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    backgroundColor: colors.surfaceMuted,
  },
  participant: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  listenBar: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  listenButton: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surfaceMuted,
  },
  listenButtonActive: { borderColor: colors.accent, backgroundColor: colors.surface },
  listenLabel: { ...typography.label, color: colors.text },
  listenLabelActive: { color: colors.accent },
  listenHint: { flex: 1, ...typography.caption, color: colors.textMuted },
  participantDot: { width: 8, height: 8, borderRadius: 4 },
  participantName: { ...typography.caption, color: colors.text },
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
  mic: {
    minHeight: 44,
    paddingHorizontal: spacing.md,
    justifyContent: "center",
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surfaceMuted,
  },
  micActive: { borderColor: colors.danger, backgroundColor: colors.surface },
  micLabel: { ...typography.label, color: colors.text },
  micLabelActive: { color: colors.danger },
  // The recording state has to be visible from across the room: red dot, live level, running clock.
  recordingStrip: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    backgroundColor: colors.surface,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  recordingDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.danger },
  levelTrack: {
    flex: 1,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.surfaceMuted,
    overflow: "hidden",
  },
  levelFill: { height: 6, borderRadius: 3, backgroundColor: colors.danger },
  recordingTime: { ...typography.caption, color: colors.text },
  recordingTimeWarn: { color: colors.warning, fontWeight: "700" },
  voiceStrip: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
  },
  voiceStripText: { ...typography.caption, color: colors.textMuted },
  voiceErrorText: { flex: 1, ...typography.caption, color: colors.danger },
  voiceHint: {
    ...typography.caption,
    color: colors.textMuted,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.sm,
  },
  linkLabel: { ...typography.caption, color: colors.accent, fontWeight: "700" },
  headerActions: { flexDirection: "row", alignItems: "center", gap: spacing.lg },
  speakRow: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  speakLabel: { ...typography.caption, color: colors.accent, fontWeight: "700" },
  headerAction: { color: colors.accent, fontSize: 15, fontWeight: "600" },
  headerActionDisabled: { color: colors.textMuted },
  pressed: { opacity: 0.7 },
  error: { color: colors.danger, paddingHorizontal: spacing.lg, paddingBottom: spacing.sm, ...typography.caption },
});
