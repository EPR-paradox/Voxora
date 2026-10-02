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

export function createReviewItem(input: CreateReviewItemInput): Promise<ReviewItem> {
  return apiRequest<ReviewItem>("/review-items", { method: "POST", body: input });
}

export function updateReviewItem(id: string, input: UpdateReviewItemInput): Promise<ReviewItem> {
  return apiRequest<ReviewItem>(`/review-items/${id}`, { method: "PATCH", body: input });
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
