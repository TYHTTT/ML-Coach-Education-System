export const COURSES = ["machine_learning", "advanced_mathematics", "linear_algebra", "probability_statistics"] as const;

export type Course = (typeof COURSES)[number];

export const COURSE_META: Record<
  Course,
  { label: string; shortLabel: string; description: string; accent: string }
> = {
  machine_learning: {
    label: "机器学习",
    shortLabel: "ML",
    description: "模型、算法与实践",
    accent: "indigo",
  },
  advanced_mathematics: {
    label: "高等数学",
    shortLabel: "∫",
    description: "极限、微积分与定理",
    accent: "cyan",
  },
  linear_algebra: { label: "线性代数", shortLabel: "Ax", description: "向量、矩阵与几何", accent: "violet" },
  probability_statistics: { label: "概率论与统计基础", shortLabel: "P", description: "概率、分布与统计", accent: "amber" },
};

export interface Source {
  source_course?: Course;
  topic_id?: string | null;
  source_id: string;
  document_id: string;
  source_file: string;
  title?: string | null;
  chapter?: string | null;
  section?: string | null;
  page?: number | null;
  chunk_index: number;
  snippet: string;
  distance?: number | null;
}

export interface ChatHistoryItem {
  role: "user" | "assistant";
  content: string;
}

export interface ChatMessage extends ChatHistoryItem {
  id: string;
  createdAt: string;
  sources?: Source[];
}

export interface ChatRequest {
  course: Course;
  message: string;
  history: ChatHistoryItem[];
  topic_id?: string;
  learning_mode?: "free_qa" | "topic_teaching" | "worked_example" | "remediation";
}

export interface ChatResponse {
  answer: string;
  course: Course;
  sources: Source[];
  retrieval_count: number;
}

export interface Conversation {
  id: string;
  course: Course;
  title: string;
  messages: ChatMessage[];
  createdAt: string;
  updatedAt: string;
}

export interface StoredChatState {
  selectedCourse: Course;
  activeConversationId: string;
  conversations: Conversation[];
}

export const TOPIC_STATUSES = [
  "locked",
  "not_started",
  "learning",
  "practicing",
  "needs_remediation",
  "ready_for_checkpoint",
  "mastered",
] as const;

export type TopicStatus = (typeof TOPIC_STATUSES)[number];

export type LearningMode = "practice" | "checkpoint";
export type PracticeDifficulty = "adaptive" | "easy" | "medium" | "hard";

export type NextAction =
  | "study_prerequisite"
  | "start_learning"
  | "teach"
  | "practice"
  | "remediate"
  | "take_checkpoint"
  | "continue_to_next_topic"
  | "course_completed"
  | string;

export interface AuthenticatedStudent {
  student_id: string;
  username: string;
  display_name: string;
  access_token: string;
  created_at: string;
}

export interface TopicPrerequisite {
  id?: string;
  topic_id?: string;
  title: string;
  required_mastery?: number;
  status?: TopicStatus;
  mastery?: number | null;
}

export interface DimensionProgress {
  dimension: string;
  label?: string;
  mastery: number | null;
  confidence?: number | null;
  evidence_count?: number;
}

export interface CurriculumTopicSummary {
  id: string;
  slug?: string;
  title: string;
  order_index?: number;
  description?: string;
  prerequisites: TopicPrerequisite[];
  status: TopicStatus;
  mastery: number | null;
  mastery_display?: string | null;
  confidence: number | null;
  evidence_count?: number;
  attempt_count?: number;
  latest_score?: number | null;
  locked_reason?: string | null;
}

export interface CurriculumTopic extends CurriculumTopicSummary {
  course: Course;
  stage: number;
  stage_title: string;
  learning_objectives: string[];
  aliases: string[];
  retrieval_keywords?: string[];
  difficulty: string;
  required_dimensions: string[];
  dimensions?: DimensionProgress[];
  active?: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface CurriculumStage {
  stage: number;
  title: string;
  topics: CurriculumTopicSummary[];
}

export interface CurriculumResponse {
  course: Course;
  stages: CurriculumStage[];
}

export interface RecentLearningAttempt {
  id?: string;
  attempt_id?: string;
  topic_id: string;
  topic_title: string;
  mode: LearningMode;
  score: number | null;
  status?: string;
  created_at: string;
}

export interface DashboardTopic {
  id: string;
  title: string;
  stage: number;
  stage_title: string;
  order_index: number;
  status: TopicStatus;
  mastery: number | null;
  confidence: number | null;
  unmet_prerequisites: string[];
}

export interface DashboardStage {
  stage: number;
  title: string;
  topics: DashboardTopic[];
}

export interface LearningDashboard {
  course: Course;
  total_topics: number;
  mastered_count: number;
  learning_count: number;
  not_started_count: number;
  locked_count: number;
  current_topic: DashboardTopic | null;
  recommended_topic_id: string | null;
  next_action: NextAction;
  reasons: string[];
  recent_practice: RecentLearningAttempt[];
  stages: DashboardStage[];
}

/** Student-visible practice option. It deliberately contains no correctness flag. */
export interface PracticeOption {
  value: string;
  label: string;
}

/**
 * Public question contract. Hidden grading material must never be added here or
 * copied into React state before submission.
 */
export interface PublicPracticeQuestion {
  question_id: string;
  position: number;
  question_type: string;
  difficulty: "easy" | "medium" | "hard" | string;
  question: string;
  options?: PracticeOption[];
  dimension_names: string[];
  max_score?: number;
  required?: boolean;
}

export interface PracticeSourceSummary {
  source_id: string;
  source_file: string;
  title?: string | null;
}

/** This is the only practice-set shape allowed into pre-submit UI state. */
export interface PublicPracticeSet {
  practice_set_id: string;
  topic_id: string;
  mode: LearningMode;
  questions: PublicPracticeQuestion[];
  source_summary: PracticeSourceSummary[];
  status?: string;
  created_at?: string;
}

export interface CreatePracticeSetRequest {
  topic_id: string;
  mode: LearningMode;
  count: number;
  difficulty: PracticeDifficulty;
}

export interface PracticeAnswer {
  question_id: string;
  answer: string;
}

export interface PracticeEvaluation {
  question_id: string;
  attempt_id?: string;
  score: number;
  verdict: string;
  correct_points: string[];
  missing_points: string[];
  misconception_tags: string[];
  feedback: string;
  reference_answer?: string | null;
  sources: Source[];
  dimension_scores?: Record<string, number>;
  evaluation_reliable?: boolean;
  evaluator_confidence?: number;
  critical_misconception?: boolean;
}

export interface MasteryGateResult {
  passed: boolean;
  mastery?: number | null;
  next_action: NextAction;
  requirements: Record<string, unknown>;
}

export interface PracticeSubmitResult {
  practice_set_id: string;
  attempt_id?: string;
  submission_id?: string;
  total_score: number;
  mastery_before: number | null;
  mastery_after: number | null;
  evaluations: PracticeEvaluation[];
  gate: MasteryGateResult;
  next_action?: NextAction;
  status?: string;
  message?: string;
  reasons?: string[];
  idempotent_replay?: boolean;
}

export interface RemediationRequest {
  topic_id: string;
  attempt_id: string;
}

export interface RemediationResponse {
  topic_id?: string;
  diagnosis: string | string[] | Record<string, unknown>;
  explanation: string;
  contrast_example?: string | null;
  targeted_question_set_id?: string | null;
  sources: Source[];
}

export interface LearningHistoryResponse {
  course: Course;
  events: RecentLearningAttempt[];
}
