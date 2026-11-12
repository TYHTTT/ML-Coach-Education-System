import type { ChatMessage, Conversation, StoredChatState } from "@/lib/types";

const STORAGE_KEY = "course-coach:chat-state:v1";
const MAX_CONVERSATIONS = 20;
const MAX_MESSAGES_PER_CONVERSATION = 80;

function makeId(prefix: string): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}_${crypto.randomUUID()}`;
  }
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2)}`;
}

export function createMessage(
  role: ChatMessage["role"],
  content: string,
  sources?: ChatMessage["sources"],
): ChatMessage {
  return {
    id: makeId("msg"),
    role,
    content,
    sources,
    createdAt: new Date().toISOString(),
  };
}

export function createConversation(): Conversation {
  const now = new Date().toISOString();
  return {
    id: makeId("chat"),
    title: "新对话",
    messages: [],
    createdAt: now,
    updatedAt: now,
  };
}

export function initialChatState(): StoredChatState {
  const conversation = createConversation();
  return {
    activeConversationId: conversation.id,
    conversations: [conversation],
  };
}

function isMessage(value: unknown): value is ChatMessage {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<ChatMessage>;
  return (
    (item.role === "user" || item.role === "assistant") &&
    typeof item.content === "string" &&
    typeof item.id === "string" &&
    typeof item.createdAt === "string"
  );
}

function isConversation(value: unknown): value is Conversation {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<Conversation>;
  return (
    typeof item.id === "string" &&
    typeof item.title === "string" &&
    Array.isArray(item.messages) &&
    item.messages.every(isMessage) &&
    typeof item.createdAt === "string" &&
    typeof item.updatedAt === "string"
  );
}

export function loadChatState(): StoredChatState {
  if (typeof window === "undefined") return initialChatState();

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return initialChatState();
    const parsed = JSON.parse(raw) as Partial<StoredChatState>;
    if (!Array.isArray(parsed.conversations)) return initialChatState();

    const conversations = parsed.conversations
      .filter(isConversation)
      .map((conversation) => ({
        id: conversation.id,
        title: conversation.title,
        createdAt: conversation.createdAt,
        updatedAt: conversation.updatedAt,
        // A legacy token may be course-scoped; rebuild context from its transcript.
        conversationToken: "course" in conversation ? undefined : typeof conversation.conversationToken === "string" ? conversation.conversationToken : undefined,
        messages: conversation.messages.slice(-MAX_MESSAGES_PER_CONVERSATION),
      }))
      .slice(0, MAX_CONVERSATIONS);

    if (conversations.length === 0) return initialChatState();

    const requestedActive = conversations.find(
      (conversation) => conversation.id === parsed.activeConversationId,
    );
    const active = requestedActive ?? conversations[0];

    return {
      activeConversationId: active.id,
      conversations,
    };
  } catch {
    return initialChatState();
  }
}

export function saveChatState(state: StoredChatState): void {
  if (typeof window === "undefined") return;
  try {
    const sorted = [...state.conversations]
      .sort(
        (left, right) =>
          new Date(right.updatedAt).getTime() - new Date(left.updatedAt).getTime(),
      )
      .slice(0, MAX_CONVERSATIONS)
      .map((conversation) => ({
        ...conversation,
        messages: conversation.messages.slice(-MAX_MESSAGES_PER_CONVERSATION),
      }));
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ ...state, conversations: sorted }),
    );
  } catch {
    // Storage can be disabled or full; chat remains available in memory.
  }
}

export function titleFromMessage(message: string): string {
  const normalized = message.replace(/\s+/g, " ").trim();
  return normalized.length > 24 ? `${normalized.slice(0, 24)}…` : normalized;
}
