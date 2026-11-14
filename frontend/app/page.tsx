"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import ChatInput from "@/components/ChatInput";
import ChatWindow from "@/components/ChatWindow";
import LearningShell from "@/components/LearningShell";
import { AlertIcon, ClockIcon, PlusIcon, TrashIcon } from "@/components/Icons";
import { useStudent } from "@/components/StudentProvider";
import { sendChat } from "@/lib/api";
import {
  createConversation,
  createMessage,
  initialChatState,
  loadChatState,
  saveChatState,
  titleFromMessage,
} from "@/lib/storage";
import type { Conversation, StoredChatState } from "@/lib/types";

const EXAMPLES = [
  { title: "理解一个概念", question: "用直观的例子解释梯度下降" },
  { title: "理清容易混淆的知识", question: "概率和似然有什么区别？" },
  { title: "一步步推导", question: "带我推导复合函数的求导法则" },
  { title: "联系实际应用", question: "线性代数在日常生活中有哪些应用？" },
];

function updateConversation(
  state: StoredChatState,
  id: string,
  updater: (conversation: Conversation) => Conversation,
): StoredChatState {
  return {
    ...state,
    conversations: state.conversations.map((conversation) =>
      conversation.id === id ? updater(conversation) : conversation,
    ),
  };
}

function relativeDate(value: string): string {
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) return "";
  const days = Math.floor(Math.max(0, Date.now() - timestamp) / 86400000);
  if (!days) return "今天";
  if (days === 1) return "昨天";
  if (days < 7) return `${days} 天前`;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
  }).format(new Date(value));
}

function HistoryPanel({
  conversations,
  activeId,
  onSelect,
  onNew,
}: {
  conversations: Conversation[];
  activeId: string;
  onSelect: (conversation: Conversation) => void;
  onNew: () => void;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col px-4 py-5">
      <button
        type="button"
        onClick={onNew}
        className="flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-indigo-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2"
      >
        <PlusIcon className="size-4" />
        新建对话
      </button>
      <h2 className="mt-6 text-xs font-semibold text-slate-500">对话历史</h2>
      <div className="chat-scrollbar mt-3 min-h-0 flex-1 space-y-1 overflow-y-auto">
        {conversations.length ? (
          conversations.map((conversation) => (
            <button
              key={conversation.id}
              type="button"
              onClick={() => onSelect(conversation)}
              aria-current={conversation.id === activeId ? "true" : undefined}
              className={`w-full rounded-xl px-3 py-3 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${conversation.id === activeId ? "bg-indigo-50 text-indigo-800" : "text-slate-600 hover:bg-slate-100"}`}
            >
              <span className="block truncate text-sm font-medium">
                {conversation.title}
              </span>
              <span className="mt-1 block text-[11px] text-slate-400">
                {relativeDate(conversation.updatedAt)}
              </span>
            </button>
          ))
        ) : (
          <p className="px-2 py-6 text-center text-xs leading-6 text-slate-400">
            开始提问后，对话会保存在这里。
          </p>
        )}
      </div>
      <p className="mt-4 shrink-0 px-2 text-[10px] leading-5 text-slate-400">
        聊天记录保存在当前浏览器中
      </p>
    </div>
  );
}

export default function HomePage() {
  const { withStudent } = useStudent();
  const [chatState, setChatState] = useState<StoredChatState>(() =>
    initialChatState(),
  );
  const [hydrated, setHydrated] = useState(false);
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [chatError, setChatError] = useState<{
    conversationId: string;
    message: string;
  } | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const historyDialog = useRef<HTMLDialogElement>(null);
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
  useEffect(() => {
    const dialog = historyDialog.current;
    if (historyOpen && dialog && !dialog.open) dialog.showModal();
    else if (!historyOpen && dialog?.open) dialog.close();
  }, [historyOpen]);
  const active =
    chatState.conversations.find(
      (conversation) => conversation.id === chatState.activeConversationId,
    ) ?? chatState.conversations[0];
  const recent = useMemo(
    () =>
      [...chatState.conversations]
        .filter((conversation) => conversation.messages.length)
        .sort(
          (a, b) =>
            new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
        ),
    [chatState.conversations],
  );
  const loading = loadingId === active?.id;
  const error =
    chatError?.conversationId === active?.id ? chatError.message : null;

  function stopRequest() {
    abortRef.current?.abort();
    abortRef.current = null;
    setLoadingId(null);
  }
  function newConversation() {
    stopRequest();
    const conversation = createConversation();
    setChatState((state) => ({
      activeConversationId: conversation.id,
      conversations: [
        conversation,
        ...state.conversations.filter((item) => item.messages.length),
      ].slice(0, 20),
    }));
    setChatError(null);
    setHistoryOpen(false);
  }
  function selectConversation(conversation: Conversation) {
    stopRequest();
    setChatState((state) => ({
      ...state,
      activeConversationId: conversation.id,
    }));
    setChatError(null);
    setHistoryOpen(false);
  }
  function clearConversation() {
    if (!active?.messages.length || !window.confirm("确定清空当前对话吗？"))
      return;
    stopRequest();
    setChatState((state) =>
      updateConversation(state, active.id, (conversation) => ({
        ...conversation,
        title: "新对话",
        messages: [],
        conversationToken: undefined,
        updatedAt: new Date().toISOString(),
      })),
    );
    setChatError(null);
  }
  async function handleSend(message: string) {
    if (!active || abortRef.current || !hydrated) return;
    const id = active.id;
    const previous = active.messages;
    const token = active.conversationToken;
    const controller = new AbortController();
    abortRef.current = controller;
    setLoadingId(id);
    setChatError(null);
    setChatState((state) =>
      updateConversation(state, id, (conversation) => ({
        ...conversation,
        title: previous.length ? conversation.title : titleFromMessage(message),
        messages: [...conversation.messages, createMessage("user", message)],
        updatedAt: new Date().toISOString(),
      })),
    );
    try {
      const response = await withStudent((studentId) =>
        sendChat(
          {
            message,
            learning_mode: "free_qa",
            history: token
              ? []
              : previous
                  .slice(-12)
                  .map(({ role, content }) => ({
                    role,
                    content: content.slice(0, 20000),
                  })),
            ...(token ? { conversation_token: token } : {}),
          },
          controller.signal,
          studentId,
        ),
      );
      if (controller.signal.aborted) return;
      setChatState((state) =>
        updateConversation(state, id, (conversation) => ({
          ...conversation,
          conversationToken: response.conversation_token ?? undefined,
          messages: [
            ...conversation.messages,
            createMessage(
              "assistant",
              response.answer || "暂时没有收到回答，请稍后重试。",
              response.sources ?? [],
            ),
          ],
          updatedAt: new Date().toISOString(),
        })),
      );
    } catch (cause) {
      if (!controller.signal.aborted)
        setChatError({
          conversationId: id,
          message:
            cause instanceof Error ? cause.message : "请求失败，请稍后重试。",
        });
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
        setLoadingId(null);
      }
    }
  }
  const historyProps = {
    conversations: recent,
    activeId: active?.id ?? "",
    onSelect: selectConversation,
    onNew: newConversation,
  };

  return (
    <LearningShell>
      <div className="flex h-[calc(100dvh-65px)] min-h-0 bg-white">
        <aside
          aria-label="对话历史"
          className="hidden w-64 shrink-0 border-r border-slate-200/70 bg-slate-50/70 lg:block"
        >
          <HistoryPanel {...historyProps} />
        </aside>
        <section aria-label="自由问答" className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-16 shrink-0 items-center justify-between gap-3 px-4 sm:px-7">
            <div className="flex min-w-0 items-center gap-3">
              <button
                type="button"
                aria-label="打开对话历史"
                onClick={() => setHistoryOpen(true)}
                className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 lg:hidden"
              >
                <ClockIcon className="size-5" />
              </button>
              {Boolean(active?.messages.length) && (
                <h1 className="truncate text-sm font-semibold text-slate-800">
                  {active.title}
                </h1>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-1">
              <button
                type="button"
                aria-label="新建对话"
                onClick={newConversation}
                className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 lg:hidden"
              >
                <PlusIcon className="size-4" />
              </button>
              <button
                type="button"
                aria-label="清空当前对话"
                onClick={clearConversation}
                disabled={!active?.messages.length}
                className="flex items-center gap-2 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700 transition hover:border-rose-300 hover:bg-rose-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:border-rose-100 disabled:bg-rose-50/50 disabled:text-rose-400"
              >
                <TrashIcon className="size-4" />
                <span>清空对话</span>
              </button>
            </div>
          </header>
          <div className="chat-scrollbar min-h-0 flex-1 overflow-y-auto overscroll-contain">
            <ChatWindow
              messages={active?.messages ?? []}
              examples={EXAMPLES}
              isLoading={loading}
              onExample={(question) => {
                if (hydrated) void handleSend(question);
              }}
            />
          </div>
          <footer className="shrink-0 bg-white px-4 pb-4 pt-2 sm:px-8 sm:pb-5">
            {error && (
              <div
                role="alert"
                className="mx-auto mb-3 flex max-w-3xl items-start gap-2 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700"
              >
                <AlertIcon className="mt-0.5 size-4 shrink-0" />
                <span className="flex-1">{error}</span>
                <button
                  type="button"
                  onClick={() => setChatError(null)}
                  className="text-xs"
                >
                  关闭
                </button>
              </div>
            )}
            <ChatInput
              key={active?.id}
              onSend={(message) => void handleSend(message)}
              disabled={!hydrated || Boolean(loadingId)}
              isLoading={loading}
              onStop={stopRequest}
              placeholder="向 Course Coach 提问…"
            />
            <p className="mt-2 text-center text-[10px] text-slate-400">
              AI 可能出错，请核实重要信息。
            </p>
          </footer>
        </section>
      </div>
      <dialog
        ref={historyDialog}
        aria-label="对话历史"
        onCancel={(event) => {
          event.preventDefault();
          setHistoryOpen(false);
        }}
        onClick={(event) => {
          if (event.target !== event.currentTarget) return;
          const bounds = event.currentTarget.getBoundingClientRect();
          if (
            event.clientX < bounds.left ||
            event.clientX > bounds.right ||
            event.clientY < bounds.top ||
            event.clientY > bounds.bottom
          )
            setHistoryOpen(false);
        }}
        className="fixed inset-y-0 left-0 m-0 h-dvh max-h-dvh w-80 max-w-[85vw] border-0 bg-slate-50 p-0 shadow-xl backdrop:bg-slate-950/25"
      >
        <div className="flex h-full min-h-0 flex-col">
          <div className="flex justify-end px-4 pt-3">
            <button
              type="button"
              aria-label="关闭对话历史"
              onClick={() => setHistoryOpen(false)}
              className="rounded-lg px-3 py-1 text-lg text-slate-500 hover:bg-slate-200"
            >
              ×
            </button>
          </div>
          <div className="min-h-0 flex-1">
            <HistoryPanel {...historyProps} />
          </div>
        </div>
      </dialog>
    </LearningShell>
  );
}
