import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { createConversation, loadChatState, saveChatState } from "../lib/storage.ts";

const originalWindow = globalThis.window;
afterEach(() => {
  if (originalWindow === undefined) delete globalThis.window;
  else globalThis.window = originalWindow;
});
function browserStorage(initial) {
  const entries = new Map([["course-coach:chat-state:v1", JSON.stringify(initial)]]);
  globalThis.window = { localStorage: { getItem: (key) => entries.get(key) ?? null, setItem: (key, value) => entries.set(key, value) } };
  return entries;
}
function conversation(id, course) {
  return { id, course, title: `旧对话 ${id}`, messages: [{ id: `msg-${id}`, role: "user", content: `保留的问题 ${id}`, createdAt: "2026-11-01T10:00:00Z" }], createdAt: "2026-11-01T10:00:00Z", updatedAt: "2026-11-01T10:00:00Z" };
}

test("merges course histories without dropping messages or the selected conversation", () => {
  const entries = browserStorage({ selectedCourse: "linear_algebra", activeConversationId: "la", conversations: [conversation("ml", "machine_learning"), conversation("math", "advanced_mathematics"), conversation("la", "linear_algebra"), conversation("prob", "probability_statistics")] });
  const state = loadChatState();
  assert.equal(state.conversations.length, 4);
  assert.equal(state.activeConversationId, "la");
  assert.equal(state.conversations[2].messages[0].content, "保留的问题 la");
  saveChatState(state);
  const saved = JSON.parse(entries.get("course-coach:chat-state:v1"));
  assert.equal("selectedCourse" in saved, false);
  assert(saved.conversations.every((item) => !("course" in item)));
  assert.equal(loadChatState().conversations.length, 4);
});

test("new conversations have no course and retain their own continuation token", () => {
  const active = createConversation();
  assert.equal("course" in active, false);
  active.conversationToken = "free-conversation-token";
  browserStorage({ activeConversationId: active.id, conversations: [active] });
  assert.equal(loadChatState().conversations[0].conversationToken, "free-conversation-token");
});

test("migration drops legacy scoped tokens while preserving the transcript", () => {
  const legacy = conversation("old", "machine_learning");
  legacy.conversationToken = "old-course-scoped-token";
  browserStorage({ activeConversationId: legacy.id, conversations: [legacy] });
  const state = loadChatState();
  assert.equal(state.conversations[0].conversationToken, undefined);
  assert.equal(state.conversations[0].messages.length, 1);
});
