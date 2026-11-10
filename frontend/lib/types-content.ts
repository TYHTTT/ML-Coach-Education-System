import type { Course, PublicPracticeSet, PracticeSubmitResult, Source, TopicStatus } from "./types";

export interface OutlineTopic {
  id: string; topic_id: string; owner_course: Course; title: string; description: string;
  learning_objectives: string[]; order_index: number; is_reference: boolean;
  status: TopicStatus; mastery: number | null; prerequisite_gap: { id: string; title: string; reason: string }[];
  can_checkpoint: boolean;
}
export interface OutlineGroup { id: string; title: string; parent_group_id: string | null; order_index: number; topics: OutlineTopic[] }
export interface CourseOutline { course: Course; title: string; groups: OutlineGroup[]; recommended_topic_id: string | null }
export interface PrerequisiteEdge {
  id: string; prerequisite_topic_id: string; dependent_topic_id: string; title: string; course: Course;
  relation_type: "required" | "recommended" | "related"; reason: string; required_competencies: string[];
  scope: "topic" | "lesson_section"; section_id?: string; satisfied: boolean; verified_competencies: string[];
}
export interface Prerequisites {
  topic_id: string; owner_course: Course; rule_version: string; can_browse: boolean; can_study: boolean; can_checkpoint: boolean;
  required: PrerequisiteEdge[]; recommended: PrerequisiteEdge[]; related: PrerequisiteEdge[]; unmet: PrerequisiteEdge[];
  successors: { id: string; title: string; course: Course; relation_type: string; reason: string }[];
}
export interface Lesson {
  id: string; topic_id: string; title: string; learning_objectives: string[]; prerequisite_summary: string;
  motivating_problem: string; key_concepts: string[]; formulas: { expression: string; symbols: string; conditions: string }[];
  worked_example_ids: string[]; practice_recommendations: string[]; summary: string; source_refs: Source[];
  content_origin: string; version: number; status: string;
}
export interface ExampleStep { step_id: string; title: string; explanation: string; formula: string; substitution: string; result: string; justification: string }
export interface WorkedExampleData {
  id: string; topic_id: string; title: string; difficulty: string; problem: string; givens: Record<string, unknown>; target: string;
  solution_outline: string; steps: ExampleStep[]; final_answer: string; verification: Record<string, unknown>;
  common_mistakes: string[]; followup_practice_ids: string[]; source_refs: Source[]; content_origin: string; version: number; status: string; family_id: string;
}
export interface Assessment extends PublicPracticeSet { purpose?: "practice" | "checkpoint" | "prerequisite_test"; result?: PracticeSubmitResult | null }
