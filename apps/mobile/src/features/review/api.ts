import { apiRequest, toQueryString } from "../../api/client";
import type {
  CreateReviewItemInput,
  ReviewItem,
  ReviewItemListResponse,
  ReviewItemStatus,
  UpdateReviewItemInput,
} from "../../api/types";

export function listReviewItems(params: { status?: ReviewItemStatus | null; due_before?: string | null } = {}) {
  const query = toQueryString({
    status: params.status,
    due_before: params.due_before,
    limit: 100,
  });
  return apiRequest<ReviewItemListResponse>(`/review-items${query}`);
}

/** One item by id (§7.10). The detail page reads it directly so a deep link works with a cold cache. */
export function getReviewItem(id: string): Promise<ReviewItem> {
  return apiRequest<ReviewItem>(`/review-items/${id}`);
}

export function createReviewItem(input: CreateReviewItemInput): Promise<ReviewItem> {
  return apiRequest<ReviewItem>("/review-items", { method: "POST", body: input });
}

export function updateReviewItem(id: string, input: UpdateReviewItemInput): Promise<ReviewItem> {
  return apiRequest<ReviewItem>(`/review-items/${id}`, { method: "PATCH", body: input });
}

/** Three consecutive recalls and the item counts as mastered. */
export const MASTERY_THRESHOLD = 3;

/**
 * The single place that turns "记住了 / 还没记住" into a PATCH body. The list and the detail screen both
 * grade items, and two copies of this ladder would drift apart the first time it changes.
 */
export function gradeReviewItemInput(item: ReviewItem, remembered: boolean): UpdateReviewItemInput {
  if (!remembered) {
    return {
      failure_count: item.failure_count + 1,
      status: "reviewing",
      due_at: nextDueDate(0),
    };
  }
  const successes = item.success_count + 1;
  return {
    success_count: successes,
    status: successes >= MASTERY_THRESHOLD ? "mastered" : "reviewing",
    due_at: nextDueDate(successes),
  };
}

/**
 * Next review date for an item the learner got right: same interval ladder the design implies
 * (short first, then longer), kept here so the screen does not invent its own dates.
 */
export function nextDueDate(successCount: number): string {
  const days = successCount <= 0 ? 1 : successCount === 1 ? 3 : successCount === 2 ? 7 : 21;
  const due = new Date();
  due.setDate(due.getDate() + days);
  return due.toISOString();
}
