import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import {
  emptyTopicChat,
  isLearningPath,
  loadTopicSessions,
  saveTopicSessions,
  topicChatKey,
} from "../lib/topic-chat-storage.ts";

const previousWindow = globalThis.window;
afterEach(() => {
  if (previousWindow === undefined) delete globalThis.window;
  else globalThis.window = previousWindow;
});
function storage() {
  const items = new Map();
  globalThis.window = {
    localStorage: {
      getItem: (key) => items.get(key) ?? null,
      setItem: (key, value) => items.set(key, value),
    },
  };
  return items;
}
const key = topicChatKey("machine_learning", "ml.machine_learning_basics");
const lesson = {
  action: "topic_teaching",
  message: "开始学习",
  response: {
    answer: "讲解正文",
    sources: [],
    course: "machine_learning",
    retrieval_count: 0,
    conversation_token: "signed-topic-conversation",
  },
};

test("reload restores lecture, conversation token and unsent practice answer in the same topic", () => {
  storage();
  const chat = {
    ...emptyTopicChat(),
    turns: [
      lesson,
      {
        ...lesson,
        action: "topic_practice",
        response: {
          ...lesson.response,
          answer: "练习题\n<details><summary>答案</summary>参考答案</details>",
        },
      },
    ],
    awaitingAnswer: true,
    inputMode: "answer",
    drafts: { clarification: "还没问完", answer: "已经写了一半的答案" },
  };
  const sessions = {
    chats: { [key]: chat },
    lastPath: "/learn/machine_learning/ml.machine_learning_basics",
  };
  assert.equal(saveTopicSessions("student-a", sessions), true);
  assert.deepEqual(loadTopicSessions("student-a"), sessions);
});

test("students and knowledge points have independent saved conversations", () => {
  storage();
  const otherKey = topicChatKey("linear_algebra", "la.vectors");
  saveTopicSessions("student-a", {
    chats: {
      [key]: { ...emptyTopicChat(), turns: [lesson] },
      [otherKey]: {
        ...emptyTopicChat(),
        drafts: { answer: "向量练习", clarification: "" },
      },
    },
    lastPath: null,
  });
  assert.deepEqual(loadTopicSessions("student-b"), {
    chats: {},
    lastPath: null,
  });
  const loaded = loadTopicSessions("student-a");
  assert.equal(
    loaded.chats[key].turns[0].response.conversation_token,
    "signed-topic-conversation",
  );
  assert.equal(loaded.chats[otherKey].turns.length, 0);
  assert.equal(loaded.chats[otherKey].drafts.answer, "向量练习");
});

test("administrator-created courses keep conversations and return locations after reload", () => {
  storage();
  const customKey = topicChatKey("physics", "physics.motion");
  const customLesson = {
    ...lesson,
    response: { ...lesson.response, course: "physics" },
  };
  const sessions = {
    chats: {
      [customKey]: {
        ...emptyTopicChat(),
        turns: [customLesson],
        drafts: { clarification: "速度的疑问", answer: "" },
      },
    },
    lastPath: "/learn/physics/physics.motion",
  };
  saveTopicSessions("student-a", sessions);
  assert.deepEqual(loadTopicSessions("student-a"), sessions);
  assert.equal(isLearningPath("/learn/physics/physics.motion"), true);
  assert.equal(isLearningPath("/learn/../physics.motion"), false);
});

test("hard reload turns an unfinished request into a retry without losing existing content", () => {
  storage();
  saveTopicSessions("student-a", {
    chats: {
      [key]: {
        ...emptyTopicChat(),
        turns: [lesson],
        pending: "topic_practice",
        pendingMessage: "我要做练习",
      },
    },
    lastPath: null,
  });
  const chat = loadTopicSessions("student-a").chats[key];
  assert.equal(chat.pending, null);
  assert.equal(chat.turns.length, 1);
  assert.equal(chat.failure.action, "topic_practice");
  assert.equal(chat.failure.message, "我要做练习");
  assert.match(chat.failure.error, /中断/);
});

test("invalid storage and unsafe return locations do not become navigation targets", () => {
  const items = storage();
  assert.equal(
    isLearningPath("https://example.com/learn/machine_learning/ml.test"),
    false,
  );
  assert.equal(
    isLearningPath("//example.com/learn/machine_learning/ml.test"),
    false,
  );
  assert.equal(isLearningPath("javascript:alert(1)"), false);
  assert.equal(
    isLearningPath(
      "/learn/linear_algebra/la.vectors?course=machine_learning&return_topic=ml.test",
    ),
    true,
  );
  saveTopicSessions("student-a", {
    chats: { [key]: { turns: [{ action: "topic_teaching", response: null }] } },
    lastPath: "//example.com",
  });
  assert.deepEqual(loadTopicSessions("student-a"), {
    chats: {},
    lastPath: null,
  });
  items.set("course-coach:topic-sessions:v1:student-a", "{broken json");
  assert.deepEqual(loadTopicSessions("student-a"), {
    chats: {},
    lastPath: null,
  });
});
