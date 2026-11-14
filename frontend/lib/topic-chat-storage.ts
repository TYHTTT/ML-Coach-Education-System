import type { ChatResponse, Course } from "./types";

export type TopicAction =
  | "topic_teaching"
  | "topic_clarification"
  | "topic_practice"
  | "topic_answer";
export type TopicInputMode = "clarification" | "answer";
export type TopicTurn = {
  action: TopicAction;
  message: string;
  response: ChatResponse;
};
export type TopicFailure = {
  action: TopicAction;
  message: string;
  error: string;
  expired: boolean;
};
export interface TopicChatState {
  turns: TopicTurn[];
  pending: TopicAction | null;
  pendingMessage: string;
  failure: TopicFailure | null;
  inputMode: TopicInputMode | null;
  drafts: { clarification: string; answer: string };
  awaitingAnswer: boolean;
}
export interface TopicSessions {
  chats: Record<string, TopicChatState>;
  lastPath: string | null;
}

const ACTIONS = new Set([
  "topic_teaching",
  "topic_clarification",
  "topic_practice",
  "topic_answer",
]);
const SCOPE = /^[a-z][a-z0-9_]{1,63}:[a-z][a-z0-9_]*\.[a-z0-9_]+$/;
export function topicChatKey(course: Course, topicId: string): string {
  return `${course}:${topicId}`;
}
export function isLearningPath(path: unknown): path is string {
  return (
    typeof path === "string" &&
    /^\/learn\/[a-z][a-z0-9_]{1,63}\/[a-z][a-z0-9_]*\.[a-z0-9_]+(?:\?[^\s#]*)?$/.test(
      path,
    )
  );
}
export function emptyTopicChat(): TopicChatState {
  return {
    turns: [],
    pending: null,
    pendingMessage: "",
    failure: null,
    inputMode: null,
    drafts: { clarification: "", answer: "" },
    awaitingAnswer: false,
  };
}
function storageKey(studentId: string): string {
  return `course-coach:topic-sessions:v1:${encodeURIComponent(studentId)}`;
}
function isTurn(value: unknown): value is TopicTurn {
  if (!value || typeof value !== "object") return false;
  const turn = value as Partial<TopicTurn>;
  return (
    ACTIONS.has(turn.action ?? "") &&
    typeof turn.message === "string" &&
    Boolean(turn.response) &&
    typeof turn.response?.answer === "string" &&
    Array.isArray(turn.response.sources)
  );
}
export function loadTopicSessions(studentId: string): TopicSessions {
  const fallback: TopicSessions = { chats: {}, lastPath: null };
  if (typeof window === "undefined" || !studentId) return fallback;
  try {
    const raw = JSON.parse(
      window.localStorage.getItem(storageKey(studentId)) || "null",
    );
    if (
      !raw ||
      typeof raw !== "object" ||
      !raw.chats ||
      typeof raw.chats !== "object"
    )
      return fallback;
    const chats: Record<string, TopicChatState> = {};
    for (const [key, value] of Object.entries(raw.chats)) {
      if (!SCOPE.test(key) || !value || typeof value !== "object") continue;
      const saved = value as Partial<TopicChatState>;
      if (!Array.isArray(saved.turns) || !saved.turns.every(isTurn)) continue;
      const interrupted =
        saved.pending &&
        ACTIONS.has(saved.pending) &&
        typeof saved.pendingMessage === "string";
      chats[key] = {
        ...emptyTopicChat(),
        turns: saved.turns,
        inputMode:
          saved.inputMode === "clarification" || saved.inputMode === "answer"
            ? saved.inputMode
            : null,
        drafts: {
          clarification:
            typeof saved.drafts?.clarification === "string"
              ? saved.drafts.clarification
              : "",
          answer:
            typeof saved.drafts?.answer === "string" ? saved.drafts.answer : "",
        },
        awaitingAnswer: saved.awaitingAnswer === true,
        failure: interrupted
          ? {
              action: saved.pending!,
              message: saved.pendingMessage!,
              expired: false,
              error: "上次请求因页面刷新而中断，请重试。",
            }
          : null,
      };
    }
    return {
      chats,
      lastPath: isLearningPath(raw.lastPath) ? raw.lastPath : null,
    };
  } catch {
    return fallback;
  }
}
export function saveTopicSessions(
  studentId: string,
  sessions: TopicSessions,
): boolean {
  if (typeof window === "undefined" || !studentId) return false;
  try {
    window.localStorage.setItem(
      storageKey(studentId),
      JSON.stringify(sessions),
    );
    return true;
  } catch {
    return false;
  }
}
