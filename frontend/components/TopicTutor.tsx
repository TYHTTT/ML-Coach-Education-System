"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { AlertIcon, SendIcon, SparklesIcon } from "@/components/Icons";
import MarkdownRenderer from "@/components/MarkdownRenderer";
import SourcePanel from "@/components/SourcePanel";
import { useStudent } from "@/components/StudentProvider";
import { sendChat } from "@/lib/api";
import type { ChatMessage, Course } from "@/lib/types";

function messageId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export default function TopicTutor({
  course,
  topicId,
  topicTitle,
  disabled = false,
  onLearningStarted,
}: {
  course: Course;
  topicId: string;
  topicTitle: string;
  disabled?: boolean;
  onLearningStarted?: () => void;
}) {
  const { withStudent } = useStudent();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const recordedRef = useRef(false);
  useEffect(() => {
    const scroll = scrollRef.current;
    if (scroll) scroll.scrollTop = scroll.scrollHeight;
  }, [messages, loading]);
  useEffect(() => {
    const input = inputRef.current;
    if (!input) return;
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 160)}px`;
  }, [question]);
  useEffect(() => { if (disabled) abortRef.current?.abort(); }, [disabled]);
  useEffect(() => () => abortRef.current?.abort(), []);

  async function ask(content: string, mode: "free_qa" | "topic_teaching" | "worked_example") {
    if (!content.trim() || loading || disabled) return;
    const userMessage: ChatMessage = {
      id: messageId(),
      role: "user",
      content: content.trim(),
      createdAt: new Date().toISOString(),
    };
    const previous = messages;
    setMessages((current) => [...current, userMessage]);
    setQuestion("");
    setError(null);
    setLoading(true);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const response = await withStudent((studentId) =>
        sendChat(
          {
            course,
            message: userMessage.content,
            topic_id: topicId,
            learning_mode: mode,
            history: previous.slice(-8).map(({ role, content: messageContent }) => ({
              role,
              content: messageContent,
            })),
          },
          controller.signal,
          studentId,
        ),
      );
      if (controller.signal.aborted) return;
      setMessages((current) => [
        ...current,
        {
          id: messageId(),
          role: "assistant",
          content: response.answer,
          sources: response.sources,
          createdAt: new Date().toISOString(),
        },
      ]);
      if (!recordedRef.current) {
        recordedRef.current = true;
        onLearningStarted?.();
      }
    } catch (cause) {
      if (!controller.signal.aborted) {
        setMessages(previous);
        setQuestion(content);
        setError(cause instanceof Error ? cause.message : "Tutor 暂时无法回答，请稍后重试。");
      }
    } finally {
      if (abortRef.current === controller) {
        setLoading(false);
        abortRef.current = null;
      }
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    void ask(question, "free_qa");
  }

  return (
    <section id="topic-tutor" aria-label="知识点 AI 对话" className="flex min-h-0 flex-1 flex-col bg-white">
      <div ref={scrollRef} role="log" aria-label="对话消息" aria-live="polite" aria-relevant="additions" className="chat-scrollbar min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 sm:px-8">
        <div className={`mx-auto flex min-h-full w-full max-w-3xl flex-col ${messages.length ? "gap-7 py-8" : "items-center justify-center py-10"}`}>
          {messages.length === 0 ? (
            <div className="max-w-lg text-center">
              <SparklesIcon className="mx-auto size-8 text-indigo-500" />
              <h2 className="mt-5 text-xl font-semibold text-slate-900 sm:text-2xl">一起学习{topicTitle}</h2>
              <p className="mt-3 text-sm leading-6 text-slate-500">从一个问题开始，也可以让我先讲解概念或举个例子。</p>
            </div>
          ) : messages.map((message) => (
            <article key={message.id} aria-label={message.role === "user" ? "你的消息" : "AI 回答"} className={message.role === "user" ? "ml-auto max-w-[90%] sm:max-w-[80%]" : "min-w-0 w-full"}>
              {message.role === "user" ? (
                <div className="whitespace-pre-wrap break-words rounded-2xl rounded-br-sm bg-slate-100 px-4 py-3 text-sm leading-7 text-slate-800">{message.content}</div>
              ) : (
                <div className="min-w-0 break-words">
                  <p className="mb-3 flex items-center gap-2 text-xs font-semibold text-indigo-600"><SparklesIcon className="size-4" />Course Coach</p>
                  <MarkdownRenderer content={message.content} />
                  {Boolean(message.sources?.length) && <details className="mt-4"><summary className="w-fit cursor-pointer text-xs text-slate-500 hover:text-indigo-600">查看 {message.sources!.length} 条资料来源</summary><div className="mt-3"><SourcePanel sources={message.sources!} /></div></details>}
                </div>
              )}
            </article>
          ))}
          {loading && <p role="status" className="flex w-full items-center gap-2 text-sm text-slate-500"><span className="size-2 animate-pulse rounded-full bg-indigo-500" />正在思考…</p>}
        </div>
      </div>

      <form onSubmit={handleSubmit} className="mx-auto w-full max-w-3xl shrink-0 px-4 pb-4 pt-2 sm:px-0 sm:pb-5">
        {error && <div role="alert" className="mb-3 flex items-start gap-2 text-xs text-rose-700"><AlertIcon className="mt-0.5 size-4 shrink-0" /><span>{error}</span></div>}
        {disabled && <p role="status" className="mb-3 text-xs leading-6 text-amber-700">测试进行中，请先独立作答。提交后可以继续对话。</p>}
        <div className="mb-3 flex flex-wrap gap-2">
          <button type="button" disabled={loading || disabled} onClick={() => void ask(`请围绕“${topicTitle}”的学习目标进行讲解，并说明关键概念、常见误区和一个例子。`, "topic_teaching")} className="rounded-full border border-slate-200 px-3 py-1.5 text-xs text-slate-600 transition hover:border-indigo-200 hover:text-indigo-700 disabled:opacity-40">知识讲解</button>
          <button type="button" disabled={loading || disabled} onClick={() => void ask(`请根据课程资料，为“${topicTitle}”出 2 道由浅入深的教学例题，给出具体题干、分步思路、推理或计算、结论及易错点，最后留一个举一反三的问题。`, "worked_example")} className="rounded-full border border-slate-200 px-3 py-1.5 text-xs text-slate-600 transition hover:border-indigo-200 hover:text-indigo-700 disabled:opacity-40">举个例子</button>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-2 shadow-sm transition focus-within:border-indigo-300 focus-within:ring-2 focus-within:ring-indigo-100">
          <label htmlFor="topic-question" className="sr-only">围绕当前知识点自由提问</label>
          <div className="flex items-end gap-2">
            <textarea ref={inputRef} id="topic-question" rows={1} maxLength={6000} value={question}
              onChange={(event) => { setQuestion(event.target.value); event.currentTarget.style.height = "auto"; event.currentTarget.style.height = `${Math.min(event.currentTarget.scrollHeight, 160)}px`; }}
              onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void ask(question, "free_qa"); } }}
              placeholder="向 Course Coach 提问…" disabled={loading || disabled}
              className="max-h-40 min-h-12 min-w-0 flex-1 resize-none bg-transparent px-3 py-3 text-sm leading-6 text-slate-800 outline-none placeholder:text-slate-400 disabled:opacity-50" />
            {loading ? <button type="button" onClick={() => abortRef.current?.abort()} aria-label="停止回答" className="mb-1 grid size-10 shrink-0 place-items-center rounded-full bg-slate-900 text-white"><span className="size-3 rounded-sm bg-white" /></button> : <button type="submit" disabled={disabled || !question.trim()} aria-label="发送问题" className="mb-1 grid size-10 shrink-0 place-items-center rounded-full bg-slate-900 text-white transition hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-30"><SendIcon className="size-4" /></button>}
          </div>
        </div>
        <p className="mt-2 text-center text-[10px] text-slate-400">Enter 发送 · Shift + Enter 换行</p>
      </form>
    </section>
  );
}
