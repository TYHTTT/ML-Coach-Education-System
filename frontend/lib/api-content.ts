import { request, sanitizePublicPracticeSet } from "./api";
import type { Course, PracticeSubmitResult, Source } from "./types";
import type { Assessment, CourseOutline, Lesson, Prerequisites, WorkedExampleData } from "./types-content";

const student = (id: string) => ({ Authorization: `Bearer ${id}` });
const jsonStudent = (id: string) => ({ ...student(id), "Content-Type": "application/json" });
export const getCourseOutline = (course: Course, id: string) => request<CourseOutline>(`/api/v1/courses/${course}/outline`, { headers: student(id) });
export const getPrerequisites = (topicId: string, id: string) => request<Prerequisites>(`/api/v1/topics/${encodeURIComponent(topicId)}/prerequisites`, { headers: student(id) });
export const getLesson = (topicId: string) => request<Lesson>(`/api/v1/topics/${encodeURIComponent(topicId)}/lesson`);
export const getExamples = (topicId: string) => request<{ examples: WorkedExampleData[] }>(`/api/v1/topics/${encodeURIComponent(topicId)}/examples`);
export const exposeExample = (example: WorkedExampleData, id: string) => request(`/api/v1/examples/${encodeURIComponent(example.id)}/exposure`, { method: "POST", headers: jsonStudent(id), body: JSON.stringify({ version: example.version }) });
export const askExample = (example: WorkedExampleData, stepId: string, question: string, id: string) => request<{ answer: string; sources: Source[] }>(`/api/v1/examples/${encodeURIComponent(example.id)}/ask`, { method: "POST", headers: jsonStudent(id), body: JSON.stringify({ version: example.version, step_id: stepId, question }) });
function publicAssessment(payload: unknown): Assessment {
  const body = payload as { purpose?: Assessment["purpose"]; result?: PracticeSubmitResult | null };
  return { ...sanitizePublicPracticeSet(payload), purpose: body.purpose, result: body.result ?? null };
}
export async function getAssessment(assessmentId: string, id: string): Promise<Assessment> {
  return publicAssessment(await request(`/api/v1/assessments/${encodeURIComponent(assessmentId)}`, { headers: student(id) }));
}
export async function createPrerequisiteTest(topicId: string, id: string, prerequisiteTopicId?: string): Promise<Assessment> {
  return publicAssessment(await request("/api/v1/prerequisite-tests", { method: "POST", headers: jsonStudent(id), body: JSON.stringify({ topic_id: topicId, prerequisite_topic_id: prerequisiteTopicId, question_count: 3 }) }));
}
