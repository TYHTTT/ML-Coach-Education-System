import type {
  AuthenticatedStudent,
  Administrator,
  AuthenticatedAdmin,
  CourseRecord,
  CourseInput,
  CourseDetail,
  CourseList,
  ChatRequest,
  ChatResponse,
  Course,
  CourseOutline,
  CurriculumResponse,
  LearningDashboard,
  CurriculumTopic,
} from "@/lib/types";

const configuredBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000";
export const API_BASE_URL = configuredBaseUrl.replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function errorCode(payload: unknown): string | undefined {
  if (!payload || typeof payload !== "object") return undefined;
  const body = payload as {
    code?: unknown;
    detail?: unknown;
    error?: { code?: unknown };
  };
  if (typeof body.error?.code === "string") return body.error.code;
  if (typeof body.code === "string") return body.code;
  if (body.detail && typeof body.detail === "object" && "code" in body.detail) {
    const code = (body.detail as { code?: unknown }).code;
    return typeof code === "string" ? code : undefined;
  }
  return undefined;
}

function errorMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object") return fallback;
  const body = payload as {
    detail?: unknown;
    message?: unknown;
    error?: { message?: unknown };
  };
  if (typeof body.error?.message === "string") return body.error.message;
  if (typeof body.detail === "string") return body.detail;
  if (
    body.detail &&
    typeof body.detail === "object" &&
    "message" in body.detail
  ) {
    const message = (body.detail as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  if (typeof body.message === "string") return body.message;
  if (Array.isArray(body.detail)) {
    return body.detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg: unknown }).msg);
        }
        return String(item);
      })
      .join("；");
  }
  return fallback;
}

export async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...init.headers,
      },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new ApiError("无法连接课程服务，请确认后端已经启动。", 0);
  }

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(
      errorMessage(payload, `请求失败（HTTP ${response.status}）`),
      response.status,
      errorCode(payload),
    );
  }
  return payload as T;
}

export function sendChat(
  payload: ChatRequest,
  signal?: AbortSignal,
  studentId?: string,
): Promise<ChatResponse> {
  return request<ChatResponse>("/api/v1/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(studentId ? { Authorization: `Bearer ${studentId}` } : {}),
    },
    body: JSON.stringify(payload),
    signal,
  });
}

function studentHeaders(studentId: string): HeadersInit {
  return { Authorization: `Bearer ${studentId}` };
}

export function isStudentNotFound(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    error.code?.toUpperCase() === "STUDENT_NOT_FOUND"
  );
}

export function registerStudent(payload: {
  username: string;
  password: string;
  display_name: string;
}): Promise<AuthenticatedStudent> {
  return request<AuthenticatedStudent>("/api/v1/students/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function loginStudent(payload: {
  username: string;
  password: string;
}): Promise<AuthenticatedStudent> {
  return request<AuthenticatedStudent>("/api/v1/students/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function logoutStudent(accessToken: string): Promise<void> {
  return request<void>("/api/v1/students/logout", {
    method: "POST",
    headers: studentHeaders(accessToken),
  });
}

export function registerAdmin(payload: {
  username: string;
  password: string;
  display_name: string;
  authcode: string;
}): Promise<AuthenticatedAdmin> {
  return request<AuthenticatedAdmin>("/api/v1/admins/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function loginAdmin(payload: {
  username: string;
  password: string;
}): Promise<AuthenticatedAdmin> {
  return request<AuthenticatedAdmin>("/api/v1/admins/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function getCurrentAdmin(
  token: string,
  signal?: AbortSignal,
): Promise<Administrator> {
  return request<Administrator>("/api/v1/admins/me", {
    headers: studentHeaders(token),
    signal,
  });
}

export function logoutAdmin(token: string): Promise<void> {
  return request<void>("/api/v1/admins/logout", {
    method: "POST",
    headers: studentHeaders(token),
  });
}

export function getCourses(signal?: AbortSignal): Promise<CourseRecord[]> {
  return request<CourseRecord[]>("/api/v1/courses", { signal });
}

export function getAdminCourses(
  token: string,
  filters: { q: string; status: string; page: number },
  signal?: AbortSignal,
): Promise<CourseList> {
  const params = new URLSearchParams({
    q: filters.q,
    status: filters.status,
    page: String(filters.page),
    page_size: "20",
  });
  return request<CourseList>(`/api/v1/admin/courses?${params}`, {
    headers: studentHeaders(token),
    signal,
  });
}

export function getAdminCourse(
  token: string,
  id: string,
  signal?: AbortSignal,
): Promise<CourseDetail> {
  return request<CourseDetail>(
    `/api/v1/admin/courses/${encodeURIComponent(id)}`,
    { headers: studentHeaders(token), signal },
  );
}

export function createCourse(
  token: string,
  payload: CourseInput,
): Promise<CourseRecord> {
  return request<CourseRecord>("/api/v1/admin/courses", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...studentHeaders(token) },
    body: JSON.stringify(payload),
  });
}

export function updateCourse(
  token: string,
  id: string,
  payload: Omit<CourseInput, "id">,
): Promise<CourseRecord> {
  return request<CourseRecord>(
    `/api/v1/admin/courses/${encodeURIComponent(id)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...studentHeaders(token) },
      body: JSON.stringify(payload),
    },
  );
}

export function deleteCourse(token: string, id: string): Promise<void> {
  return request<void>(`/api/v1/admin/courses/${encodeURIComponent(id)}`, {
    method: "DELETE",
    headers: studentHeaders(token),
  });
}

export function getCurriculum(
  course: Course,
  studentId?: string,
): Promise<CurriculumResponse> {
  return request<CurriculumResponse>(
    `/api/v1/curriculum/topics?course=${encodeURIComponent(course)}`,
    studentId ? { headers: studentHeaders(studentId) } : {},
  );
}

function normalizeTopic(payload: unknown): CurriculumTopic {
  const body = asRecord(payload);
  const rawDimensions = body.dimensions;
  const dimensions = Array.isArray(rawDimensions)
    ? rawDimensions.map((item) => {
        const dimension = asRecord(item);
        return {
          dimension: String(dimension.dimension ?? ""),
          label:
            typeof dimension.label === "string" ? dimension.label : undefined,
          mastery:
            typeof dimension.mastery === "number" ? dimension.mastery : null,
          confidence:
            typeof dimension.confidence === "number"
              ? dimension.confidence
              : null,
          evidence_count:
            typeof dimension.evidence_count === "number"
              ? dimension.evidence_count
              : 0,
        };
      })
    : Object.entries(asRecord(rawDimensions)).map(([name, value]) => {
        const dimension = asRecord(value);
        return {
          dimension: name,
          mastery:
            typeof dimension.mastery === "number" ? dimension.mastery : null,
          confidence:
            typeof dimension.confidence === "number"
              ? dimension.confidence
              : null,
          evidence_count:
            typeof dimension.evidence_count === "number"
              ? dimension.evidence_count
              : 0,
        };
      });
  return {
    id: String(body.id ?? ""),
    course: String(body.course ?? "machine_learning") as Course,
    slug: typeof body.slug === "string" ? body.slug : undefined,
    title: String(body.title ?? ""),
    stage: Number(body.stage ?? 0),
    stage_title: String(body.stage_title ?? ""),
    order_index:
      typeof body.order_index === "number" ? body.order_index : undefined,
    description:
      typeof body.description === "string" ? body.description : undefined,
    learning_objectives: strings(body.learning_objectives),
    aliases: strings(body.aliases),
    retrieval_keywords: strings(body.retrieval_keywords),
    difficulty: String(body.difficulty ?? "medium"),
    required_dimensions: strings(body.required_dimensions),
    status: (typeof body.status === "string"
      ? body.status
      : "not_started") as CurriculumTopic["status"],
    mastery: typeof body.mastery === "number" ? body.mastery : null,
    mastery_display:
      typeof body.mastery_display === "string" ? body.mastery_display : null,
    confidence: typeof body.confidence === "number" ? body.confidence : null,
    evidence_count:
      typeof body.evidence_count === "number" ? body.evidence_count : undefined,
    attempt_count:
      typeof body.attempt_count === "number" ? body.attempt_count : undefined,
    latest_score:
      typeof body.latest_score === "number" ? body.latest_score : null,
    dimensions,
    active: typeof body.active === "boolean" ? body.active : undefined,
    created_at:
      typeof body.created_at === "string" ? body.created_at : undefined,
    updated_at:
      typeof body.updated_at === "string" ? body.updated_at : undefined,
  };
}

export async function getTopic(
  topicId: string,
  studentId?: string,
): Promise<CurriculumTopic> {
  const response = await request<unknown>(
    `/api/v1/curriculum/topics/${encodeURIComponent(topicId)}`,
    studentId ? { headers: studentHeaders(studentId) } : {},
  );
  return normalizeTopic(response);
}

export async function getLearningDashboard(
  course: Course,
  studentId: string,
): Promise<LearningDashboard> {
  const response = await request<unknown>(
    `/api/v1/learning/dashboard?course=${encodeURIComponent(course)}`,
    { headers: studentHeaders(studentId) },
  );
  const body = asRecord(response);
  const rawRecent = Array.isArray(body.recent_practice)
    ? body.recent_practice
    : Array.isArray(body.recent_attempts)
      ? body.recent_attempts
      : [];
  return {
    course,
    total_topics: Number(body.total_topics ?? 0),
    mastered_count: Number(body.mastered_count ?? 0),
    learning_count: Number(body.learning_count ?? 0),
    not_started_count: Number(body.not_started_count ?? 0),
    current_topic:
      body.current_topic && typeof body.current_topic === "object"
        ? (body.current_topic as LearningDashboard["current_topic"])
        : null,
    recommended_topic_id:
      typeof body.recommended_topic_id === "string"
        ? body.recommended_topic_id
        : null,
    next_action:
      typeof body.next_action === "string"
        ? body.next_action
        : "start_learning",
    reasons: strings(body.reasons),
    recent_practice: rawRecent.map((item) => {
      const attempt = asRecord(item);
      return {
        id: typeof attempt.id === "string" ? attempt.id : undefined,
        attempt_id:
          typeof attempt.attempt_id === "string"
            ? attempt.attempt_id
            : undefined,
        topic_id: String(attempt.topic_id ?? ""),
        topic_title: String(
          attempt.topic_title ??
            attempt.title ??
            attempt.topic_id ??
            "练习记录",
        ),
        mode: attempt.mode === "checkpoint" ? "checkpoint" : "practice",
        score:
          typeof attempt.score === "number"
            ? attempt.score
            : typeof attempt.total_score === "number"
              ? attempt.total_score
              : null,
        status: typeof attempt.status === "string" ? attempt.status : undefined,
        created_at: String(attempt.created_at ?? attempt.submitted_at ?? ""),
      };
    }),
    stages: Array.isArray(body.stages)
      ? (body.stages as LearningDashboard["stages"])
      : [],
  };
}

export async function startTopic(
  topicId: string,
  studentId: string,
): Promise<CurriculumTopic> {
  const response = await request<unknown>(
    `/api/v1/learning/topics/${encodeURIComponent(topicId)}/start`,
    { method: "POST", headers: studentHeaders(studentId) },
  );
  const body = asRecord(response);
  return normalizeTopic(
    body.topic && typeof body.topic === "object" ? body.topic : body,
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object"
    ? (value as Record<string, unknown>)
    : {};
}

function strings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

export function getCourseOutline(
  course: Course,
  studentId?: string,
): Promise<CourseOutline> {
  return request<CourseOutline>(
    `/api/v1/courses/${encodeURIComponent(course)}/outline`,
    studentId ? { headers: studentHeaders(studentId) } : {},
  );
}
