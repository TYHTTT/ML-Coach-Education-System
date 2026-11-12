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
  source_course?: Course | null;
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
  course?: Course;
  message: string;
  history: ChatHistoryItem[];
  topic_id?: string;
  conversation_token?: string;
  learning_mode?: "free_qa" | "topic_teaching" | "topic_clarification" | "topic_practice" | "topic_answer";
}

export interface ChatResponse {
  answer: string;
  course: Course | null;
  sources: Source[];
  retrieval_count: number;
  conversation_token?: string | null;
}

export interface Conversation {
  id: string;
  conversationToken?: string;
  title: string;
  messages: ChatMessage[];
  createdAt: string;
  updatedAt: string;
}

export interface StoredChatState {
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

export interface Administrator {
  admin_id: string;
  username: string;
  display_name: string;
  role: "admin";
  created_at: string;
  last_active_at: string;
}

export interface AuthenticatedAdmin extends Administrator {
  access_token: string;
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
  mode: "practice" | "checkpoint";
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

export interface OutlineTopic {
  id: string;
  topic_id: string;
  owner_course: Course;
  title: string;
  description: string;
  learning_objectives: string[];
  order_index: number;
  is_reference: boolean;
  status: TopicStatus;
  mastery: number | null;
  prerequisite_gap: { id: string; title: string; reason: string }[];
}

export interface OutlineGroup {
  id: string;
  title: string;
  parent_group_id: string | null;
  order_index: number;
  topics: OutlineTopic[];
}

export interface CourseOutline {
  course: Course;
  title: string;
  groups: OutlineGroup[];
  recommended_topic_id: string | null;
}
