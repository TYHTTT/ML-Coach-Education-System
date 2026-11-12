import { request } from "@/lib/api";

export interface TopicValues {
  title: string; description: string; stage: number; stage_title: string;
  learning_objectives: string[]; aliases: string[]; retrieval_keywords: string[];
  difficulty: "easy" | "medium" | "hard"; prerequisite_ids: string[];
}
export interface ManagedTopic extends TopicValues {
  id: string; course: string; owner_title: string; is_reference: boolean; active: boolean; available: boolean;
  parent_group_id: string;
}
export interface TopicGroup { id: string; title: string; stage: number | null; topics: ManagedTopic[] }
export interface ManagedOutline {
  course: { id: string; title: string; active: boolean }; groups: TopicGroup[]; removed_topics: ManagedTopic[];
}
export interface TopicCandidate { id: string; title: string; course: string; course_title: string }
export function topicCatalog(token: string, signal?: AbortSignal) {
  return request<TopicCandidate[]>("/api/v1/admin/topics", { headers: { Authorization: `Bearer ${token}` }, signal });
}
export function manageTopics(token: string, course: string, method = "GET", suffix = "", body?: unknown, signal?: AbortSignal) {
  return request<ManagedOutline>(`/api/v1/admin/courses/${encodeURIComponent(course)}/topics${suffix}`, {
    method, signal, headers: { Authorization: `Bearer ${token}`, ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
}
