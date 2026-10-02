/**
 * DTOs mirroring the backend schemas (`backend/app/*_schemas.py`).
 *
 * Field names stay `snake_case` on purpose: the wire format is the contract (design §4.2), and a
 * camelCase layer in between would drift silently every time the API changes. Renaming happens only
 * where the UI genuinely needs a different shape, and never on the wire.
 */

export type ScenarioCategory = "interview" | "workplace" | "travel" | "daily_life";

export type SessionStatus = "active" | "completed" | "abandoned";

export type MessageRole = "user" | "assistant";

export type MessageStatus = "pending" | "completed" | "failed";

export type EvaluationStatus = "pending" | "processing" | "completed" | "failed";

export type ReviewItemType = "expression" | "grammar" | "clarity" | "pronunciation" | "communication";

export type ReviewItemStatus = "new" | "reviewing" | "mastered" | "archived";

export interface ScenarioSummary {
  id: string;
  slug: string;
  title: string;
  summary: string;
  category: ScenarioCategory;
  industry_segment: string | null;
  companies: string[];
  roles: string[];
  difficulty: number;
  estimated_minutes: number;
  target_skills: string[];
}

export interface AiCharacter {
  name?: string;
  title?: string;
  personality?: string;
  communication_style?: string;
}

export interface TargetExpression {
  expression?: string;
  meaning?: string;
  usage?: string;
}

export interface ScenarioDetail extends ScenarioSummary {
  situation: string;
  ai_character: AiCharacter;
  user_objective: string;
  target_expressions: TargetExpression[];
  /** Participants of a meeting scenario; null means a single-character scenario. */
  cast: ScenarioParticipant[] | null;
}

export interface ScenarioReference {
  id: string;
  title: string;
}

export interface ScenarioListResponse {
  items: ScenarioSummary[];
  total: number;
  limit: number;
  offset: number;
}

/**
 * One person in the room (design §7.4 / meeting-mode §4). `key` is what messages carry; `name` and
 * `title` are display data taken from the session's own snapshot.
 */
export interface ScenarioParticipant {
  key: string;
  name: string;
  title: string;
}

export interface PracticeMessage {
  id: string;
  client_message_id?: string | null;
  turn_index: number;
  /** Display order inside the session: sort by this, not by array position (meeting-mode §3). */
  seq: number;
  role: MessageRole;
  /** "" for the learner, otherwise a participant key. Never null. */
  speaker_key: string;
  speaker: ScenarioParticipant | null;
  content: string;
  created_at: string;
}

export interface PracticeMessageDetail extends PracticeMessage {
  status: MessageStatus;
}

export interface OpeningMessage {
  id: string;
  turn_index: number;
  seq: number;
  role: "assistant";
  speaker_key: string;
  speaker: ScenarioParticipant | null;
  content: string;
  status: "completed";
}

export interface PracticeSessionCreated {
  id: string;
  scenario: ScenarioReference;
  status: "active";
  input_mode: "text";
  /** Who is in the room. One entry for a single-character scenario, two or three in a meeting. */
  participants: ScenarioParticipant[];
  messages: OpeningMessage[];
  started_at: string;
}

export interface PracticeSessionDetail {
  id: string;
  scenario: ScenarioReference;
  status: SessionStatus;
  input_mode: "text" | "voice";
  scenario_version: number;
  turn_count: number;
  participants: ScenarioParticipant[];
  messages: PracticeMessageDetail[];
  started_at: string;
  completed_at: string | null;
}

export interface PracticeSessionSummary {
  id: string;
  scenario: ScenarioReference;
  status: SessionStatus;
  turn_count: number;
  evaluation_status: EvaluationStatus | null;
  started_at: string;
  last_activity_at: string;
  completed_at: string | null;
}

export interface PracticeSessionListResponse {
  items: PracticeSessionSummary[];
  total: number;
  limit: number;
  offset: number;
}

/** What a transcription returns (design §7.11): text plus the metadata §8.6 wants traceable. */
export interface TranscriptionResponse {
  text: string;
  language: string;
  duration_ms: number | null;
  provider: string;
  model: string;
}

export interface SendPracticeMessageResponse {
  user_message: PracticeMessage;
  /** Always a list: a meeting answers with one turn per participant that speaks (meeting-mode §5). */
  assistant_messages: PracticeMessage[];
  session_status: "active";
}

export interface EvaluationDimension {
  rating: "strong" | "developing" | "needs_work";
  evidence: string[];
  feedback: string;
}

export interface SuggestedRephrase {
  original: string;
  suggestion: string;
  reason: string;
}

export interface EvaluationReviewItem {
  item_type: string;
  original_text: string;
  target_text: string;
  explanation: string;
}

export interface EvaluationPayload {
  rubric_version: string;
  summary: string;
  dimensions: Partial<Record<"clarity" | "fluency" | "naturalness" | "professional_tone" | "response_relevance", EvaluationDimension>>;
  strengths: string[];
  improvements: string[];
  suggested_rephrases: SuggestedRephrase[];
  review_items: EvaluationReviewItem[];
}

/**
 * One shape for finish, retry and read (design §7.8): a failed report arrives here with
 * `evaluation_status: "failed"` and an `error_code`, never as a transport error.
 */
export interface EvaluationStatusResponse {
  session_id: string;
  session_status: SessionStatus;
  evaluation_status: EvaluationStatus;
  evaluation: EvaluationPayload | null;
  error_code: string | null;
  retryable: boolean;
  attempt_count: number;
  completed_at: string | null;
}

export interface ReviewItem {
  id: string;
  source_session_id: string | null;
  source_message_id: string | null;
  item_type: ReviewItemType;
  original_text: string | null;
  target_text: string;
  explanation: string | null;
  status: ReviewItemStatus;
  due_at: string | null;
  success_count: number;
  failure_count: number;
  created_at: string;
  updated_at: string;
}

export interface ReviewItemListResponse {
  items: ReviewItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface CreateReviewItemInput {
  source_session_id: string;
  source_message_id?: string | null;
  item_type: ReviewItemType;
  original_text?: string | null;
  target_text: string;
  explanation?: string | null;
  due_at?: string | null;
}

export interface UpdateReviewItemInput {
  status?: ReviewItemStatus;
  due_at?: string | null;
  success_count?: number;
  failure_count?: number;
}

/** Payload of the `{ error: {...} }` envelope every non-2xx response uses. */
export interface ApiErrorBody {
  code: string;
  message: string;
  request_id?: string;
  details?: Record<string, unknown>;
}
