import type {
  PracticeMessage,
  PracticeMessageDetail,
  PracticeSessionDetail,
  SendPracticeMessageResponse,
} from "../../api/types";

/**
 * The list key a message keeps for its whole life (§10.3).
 *
 * The learner's own turn exists twice: first as a local outbox row keyed by `client_message_id`, then as
 * the server row that carries the same id. Keying the server row by that id too means React hands the row
 * over instead of unmounting one and mounting a fresh one in the same frame — which is exactly the blink
 * the learner sees when the optimistic bubble disappears and the fetched copy arrives.
 */
export function messageKey(message: { id: string; client_message_id?: string | null }): string {
  return message.client_message_id ?? message.id;
}

/**
 * Fold one exchange into the cached session.
 *
 * Without this the screen has a hole between "the optimistic row is dropped" and "the refetch has landed":
 * the message that was just sent vanishes for the length of a round trip and then comes back. Both halves
 * of the update then happen in one render, so the bubble is only ever added to.
 *
 * Existing ids are replaced rather than appended, so a replayed `client_message_id` (retry, §7.6) lands on
 * the row already on screen. Messages arrive `completed`, which is what the next refetch would say too
 * (`send_practice_message` commits both sides of the exchange in one transaction).
 */
export function mergeExchange(
  session: PracticeSessionDetail,
  exchange: SendPracticeMessageResponse,
): PracticeSessionDetail {
  const byId = new Map<string, PracticeMessageDetail>(
    session.messages.map((message) => [message.id, message]),
  );
  let learnedTurns = 0;
  for (const message of [exchange.user_message, ...exchange.assistant_messages]) {
    if (byId.has(message.id)) continue;
    if (message.role === "user") learnedTurns += 1;
    byId.set(message.id, toDetail(message));
  }
  return {
    ...session,
    messages: [...byId.values()].sort((left, right) => left.seq - right.seq),
    // The learner's turn is what `turn_count` counts: listening (`advance`) never moves it (§7.14), and the
    // screen reads it to choose between 结束 -> 报告 and 结束 -> 返回.
    turn_count: session.turn_count + learnedTurns,
  };
}

/** A response message is the detail shape minus `status`, and a written turn is a completed one. */
function toDetail(message: PracticeMessage): PracticeMessageDetail {
  return { ...message, status: "completed" };
}
