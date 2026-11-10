"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import ChatInput from "@/components/ChatInput";
import ChatWindow from "@/components/ChatWindow";
import CourseSelector from "@/components/CourseSelector";
import LearningShell from "@/components/LearningShell";
import {
  AlertIcon,
  ClockIcon,
  DatabaseIcon,
  PlusIcon,
  TrashIcon,
} from "@/components/Icons";
import SourcePanel from "@/components/SourcePanel";
import { sendChat } from "@/lib/api";
import {
  createConversation,
  createMessage,
  initialChatState,
  loadChatState,
  saveChatState,
  titleFromMessage,
} from "@/lib/storage";
import {
  COURSE_META,
  type ChatHistoryItem,
  type Conversation,
  type Course,
  type StoredChatState,
} from "@/lib/types";

const EXAMPLES: Record<Course, string[]> = {
  machine_learning: [
    "什么是过拟合？",
    "为什么逻辑回归使用交叉熵？",
    "梯度下降是如何更新参数的？",
    "决策树为什么容易过拟合？",
  ],
  advanced_mathematics: [
    "导数的几何意义是什么？",
    "为什么连续不一定可导？",
    "如何理解定积分？",
    "拉格朗日中值定理解决什么问题？",
  ],
  linear_algebra: ["怎样检查矩阵乘法的维度？", "向量内积与模型预测有什么关系？", "如何理解正交投影？"],
  probability_statistics: ["条件概率的分母为什么是条件事件？", "期望与方差分别描述什么？", "似然和概率有什么区别？"],
};

interface ChatError {
  conversationId: string;
  message: string;
}

function updateConversation(
  state: StoredChatState,
  conversationId: string,
  updater: (conversation: Conversation) => Conversation,
): StoredChatState {
  return {
    ...state,
    conversations: state.conversations.map((conversation) =>
      conversation.id === conversationId ? updater(conversation) : conversation,
    ),
  };
}

function relativeDate(value: string): string {
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return "";
  const minutes = Math.max(0, Math.floor((Date.now() - then) / 60_000));
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} 天前`;
  return new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric" }).format(new Date(value));
}

export default function HomePage() {
  const [chatState, setChatState] = useState<StoredChatState>(() => initialChatState());
  const [hydrated, setHydrated] = useState(false);
  const [loadingConversationId, setLoadingConversationId] = useState<string | null>(null);
  const [chatError, setChatError] = useState<ChatError | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setChatState(loadChatState());
      setHydrated(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (hydrated) saveChatState(chatState);
  }, [chatState, hydrated]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const activeConversation = useMemo(
    () =>
      chatState.conversations.find(
        (conversation) => conversation.id === chatState.activeConversationId,
      ) ?? chatState.conversations[0],
    [chatState],
  );

  const recentConversations = useMemo(
    () =>
      [...chatState.conversations]
        .filter((conversation) => conversation.messages.length > 0)
        .sort(
          (left, right) =>
            new Date(right.updatedAt).getTime() - new Date(left.updatedAt).getTime(),
        )
        .slice(0, 8),
    [chatState.conversations],
  );

  const latestAssistant = useMemo(
    () =>
      [...(activeConversation?.messages ?? [])]
        .reverse()
        .find((message) => message.role === "assistant"),
    [activeConversation],
  );

  const currentCourse = activeConversation?.course ?? chatState.selectedCourse;
  const isCurrentLoading = loadingConversationId === activeConversation?.id;
  const currentError = chatError?.conversationId === activeConversation?.id ? chatError.message : null;

  function stopActiveRequest() {
    abortRef.current?.abort();
    abortRef.current = null;
    setLoadingConversationId(null);
  }

  function startNewConversation(course = currentCourse) {
    stopActiveRequest();
    const conversation = createConversation(course);
    setChatState((state) => ({
      selectedCourse: course,
      activeConversationId: conversation.id,
      conversations: [conversation, ...state.conversations].slice(0, 20),
    }));
    setChatError(null);
  }

  function selectCourse(course: Course) {
    if (course === currentCourse) return;
    setChatState((state) => {
      const match = [...state.conversations]
        .filter((conversation) => conversation.course === course)
        .sort(
          (left, right) =>
            new Date(right.updatedAt).getTime() - new Date(left.updatedAt).getTime(),
        )[0];
      if (match) {
        return { ...state, selectedCourse: course, activeConversationId: match.id };
      }
      const conversation = createConversation(course);
      return {
        selectedCourse: course,
        activeConversationId: conversation.id,
        conversations: [conversation, ...state.conversations],
      };
    });
    setChatError(null);
  }

  function selectConversation(conversation: Conversation) {
    setChatState((state) => ({
      ...state,
      selectedCourse: conversation.course,
      activeConversationId: conversation.id,
    }));
    setChatError(null);
  }

  function clearCurrentConversation() {
    if (!activeConversation || activeConversation.messages.length === 0) return;
    if (!window.confirm("确定清空当前聊天记录吗？此操作只影响这个对话。")) return;
    stopActiveRequest();
    setChatState((state) =>
      updateConversation(state, activeConversation.id, (conversation) => ({
        ...conversation,
        title: "新对话",
        messages: [],
        updatedAt: new Date().toISOString(),
      })),
    );
    setChatError(null);
  }

  async function handleSend(message: string) {
    if (!activeConversation || loadingConversationId) return;

    const conversationId = activeConversation.id;
    const requestCourse = activeConversation.course;
    const previousMessages = activeConversation.messages;
    const userMessage = createMessage("user", message);
    const now = new Date().toISOString();

    setChatState((state) =>
      updateConversation(state, conversationId, (conversation) => ({
        ...conversation,
        title: conversation.messages.length === 0 ? titleFromMessage(message) : conversation.title,
        messages: [...conversation.messages, userMessage],
        updatedAt: now,
      })),
    );
    setChatError(null);
    setLoadingConversationId(conversationId);

    const controller = new AbortController();
    abortRef.current = controller;
    const history: ChatHistoryItem[] = previousMessages
      .slice(-12)
      .map(({ role, content }) => ({ role, content }));

    try {
      const response = await sendChat(
        { course: requestCourse, message, history },
        controller.signal,
      );
      const assistantMessage = createMessage(
        "assistant",
        response.answer || "课程服务没有返回有效答案，请稍后重试。",
        response.sources ?? [],
      );
      setChatState((state) =>
        updateConversation(state, conversationId, (conversation) => ({
          ...conversation,
          messages: [...conversation.messages, assistantMessage],
          updatedAt: new Date().toISOString(),
        })),
      );
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        setChatError({
          conversationId,
          message: error instanceof Error ? error.message : "请求失败，请稍后重试。",
        });
      }
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
        setLoadingConversationId(null);
      }
    }
  }

  return (
    <LearningShell>
      <div className="h-[calc(100svh-73px)] min-h-[547px] overflow-hidden bg-canvas lg:grid lg:grid-cols-[272px_minmax(0,1fr)] xl:grid-cols-[272px_minmax(0,1fr)_352px]">
      <aside className="hidden h-full flex-col border-r border-slate-200 bg-white/85 px-4 py-5 backdrop-blur lg:flex">
        <button
          type="button"
          onClick={() => startNewConversation()}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-500 focus-visible:ring-offset-2"
        >
          <PlusIcon className="size-4" />
          新建对话
        </button>

        <div className="mt-6">
          <p className="mb-2 px-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400">课程</p>
          <CourseSelector value={currentCourse} onChange={selectCourse} />
        </div>

        <div className="mt-6 min-h-0 flex-1">
          <div className="mb-2 flex items-center justify-between px-2">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400">最近聊天</p>
            <span className="text-[10px] tabular-nums text-slate-400">{recentConversations.length}/8</span>
          </div>
          <div className="chat-scrollbar max-h-full space-y-1 overflow-y-auto pr-1">
            {recentConversations.length === 0 ? (
              <p className="rounded-xl border border-dashed border-slate-200 px-3 py-4 text-center text-xs leading-5 text-slate-400">
                发送第一个问题后，聊天会保存在此浏览器中。
              </p>
            ) : (
              recentConversations.map((conversation) => (
                <button
                  key={conversation.id}
                  type="button"
                  onClick={() => selectConversation(conversation)}
                  className={`w-full rounded-xl px-3 py-2.5 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${
                    conversation.id === activeConversation?.id
                      ? "bg-slate-100 text-slate-900"
                      : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                  }`}
                >
                  <span className="block truncate text-xs font-medium">{conversation.title}</span>
                  <span className="mt-1 flex items-center gap-1.5 text-[10px] text-slate-400">
                    <span>{COURSE_META[conversation.course].label}</span>
                    <span>·</span>
                    <span>{relativeDate(conversation.updatedAt)}</span>
                  </span>
                </button>
              ))
            )}
          </div>
        </div>

      </aside>

      <section className="app-grid-bg flex h-full min-w-0 flex-col">
        <header className="z-10 shrink-0 border-b border-slate-200/80 bg-white/85 px-4 py-3 backdrop-blur-xl sm:px-6">
          <div className="flex items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-3">
              <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-indigo-600 text-xs font-bold text-white lg:hidden">
                {COURSE_META[currentCourse].shortLabel}
              </span>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <h2 className="truncate text-sm font-semibold text-slate-900 sm:text-base">
                    {COURSE_META[currentCourse].label}
                  </h2>
                  <span className="hidden rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700 sm:inline-flex">
                    AI Tutor
                  </span>
                </div>
                <p className="truncate text-[11px] text-slate-400">{activeConversation?.title ?? "新对话"}</p>
              </div>
            </div>
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => startNewConversation()}
                className="inline-flex size-9 items-center justify-center rounded-xl text-slate-500 transition hover:bg-slate-100 hover:text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 lg:hidden"
                aria-label="新建对话"
              >
                <PlusIcon className="size-4.5" />
              </button>
              <button
                type="button"
                onClick={clearCurrentConversation}
                disabled={!activeConversation?.messages.length}
                className="inline-flex items-center gap-2 rounded-xl px-2.5 py-2 text-xs font-medium text-slate-500 transition hover:bg-rose-50 hover:text-rose-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400 disabled:cursor-not-allowed disabled:opacity-35 disabled:hover:bg-transparent disabled:hover:text-slate-500 sm:px-3"
                title="清空当前聊天"
              >
                <TrashIcon className="size-3.5" />
                <span className="hidden sm:inline">清空当前聊天</span>
              </button>
            </div>
          </div>

          <div className="mt-3 lg:hidden">
            <CourseSelector value={currentCourse} onChange={selectCourse} compact />
          </div>

          {recentConversations.length > 0 && (
            <details className="group mt-2 lg:hidden">
              <summary className="flex cursor-pointer list-none items-center gap-1 text-[11px] font-medium text-slate-400 [&::-webkit-details-marker]:hidden">
                <ClockIcon className="size-3" /> 最近聊天
                <span className="transition group-open:rotate-180" aria-hidden="true">⌄</span>
              </summary>
              <div className="mt-2 flex gap-2 overflow-x-auto pb-1">
                {recentConversations.slice(0, 5).map((conversation) => (
                  <button
                    key={conversation.id}
                    type="button"
                    onClick={() => selectConversation(conversation)}
                    className={`max-w-48 shrink-0 truncate rounded-lg border px-3 py-1.5 text-xs ${
                      conversation.id === activeConversation?.id
                        ? "border-indigo-200 bg-indigo-50 text-indigo-700"
                        : "border-slate-200 bg-white text-slate-600"
                    }`}
                  >
                    {conversation.title}
                  </button>
                ))}
              </div>
            </details>
          )}
        </header>

        <div className="chat-scrollbar min-h-0 flex-1 overflow-y-auto">
          <ChatWindow
            messages={activeConversation?.messages ?? []}
            course={currentCourse}
            examples={EXAMPLES[currentCourse]}
            isLoading={isCurrentLoading}
            onExample={(question) => void handleSend(question)}
          />
        </div>

        <footer className="shrink-0 border-t border-slate-200/70 bg-white/85 px-4 py-3 backdrop-blur-xl sm:px-6 sm:py-4">
          {currentError && (
            <div className="mx-auto mb-2.5 flex max-w-4xl items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2.5 text-sm text-rose-800" role="alert">
              <AlertIcon className="mt-0.5 size-4 shrink-0" />
              <span className="flex-1">{currentError}</span>
              <button type="button" onClick={() => setChatError(null)} className="text-xs font-medium text-rose-600 hover:text-rose-800">关闭</button>
            </div>
          )}
          <ChatInput
            onSend={(message) => void handleSend(message)}
            disabled={Boolean(loadingConversationId)}
            placeholder={`向${COURSE_META[currentCourse].label} Tutor 提问…`}
          />
          <p className="mt-2 text-center text-[10px] text-slate-400">
            Tutor 可能出错，请结合课程原文核验关键信息。
          </p>
        </footer>
      </section>

      <aside className="chat-scrollbar hidden h-svh overflow-y-auto border-l border-slate-200 bg-slate-50/80 p-5 xl:block">
        <div className="sticky top-0">
          <div className="mb-4 flex items-center gap-2">
            <span className="grid size-8 place-items-center rounded-xl bg-indigo-100 text-indigo-700">
              <DatabaseIcon className="size-4" />
            </span>
            <div>
              <h2 className="text-sm font-semibold text-slate-800">资料来源</h2>
              <p className="text-[11px] text-slate-400">最近一次 Tutor 回答</p>
            </div>
          </div>
          <SourcePanel sources={latestAssistant?.sources ?? []} />
        </div>
      </aside>
      </div>
    </LearningShell>
  );
}
