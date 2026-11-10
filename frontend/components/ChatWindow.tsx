"use client";

import { useEffect, useRef } from "react";
import ChatMessage from "@/components/ChatMessage";
import { SparklesIcon } from "@/components/Icons";
import { COURSE_META, type ChatMessage as ChatMessageType, type Course } from "@/lib/types";

interface ChatWindowProps {
  messages: ChatMessageType[];
  course: Course;
  examples: string[];
  isLoading: boolean;
  onExample: (question: string) => void;
}

function ThinkingIndicator() {
  return (
    <div className="flex animate-fade-up items-start gap-3" role="status" aria-label="Tutor 正在整理回答">
      <div className="mt-0.5 hidden size-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-indigo-600 to-violet-600 text-white shadow-sm sm:grid">
        <SparklesIcon className="size-4.5" />
      </div>
      <div className="rounded-2xl rounded-tl-md border border-slate-200 bg-white px-5 py-4 shadow-soft">
        <div className="flex items-center gap-3">
          <div className="flex gap-1.5" aria-hidden="true">
            {[0, 1, 2].map((index) => (
              <span
                key={index}
                className="size-1.5 animate-pulse-dot rounded-full bg-indigo-500"
                style={{ animationDelay: `${index * 150}ms` }}
              />
            ))}
          </div>
          <span className="text-sm text-slate-500">正在检索课程资料并组织答案…</span>
        </div>
      </div>
    </div>
  );
}

export default function ChatWindow({
  messages,
  course,
  examples,
  isLoading,
  onExample,
}: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages.length, isLoading]);

  if (messages.length === 0 && !isLoading) {
    return (
      <div className="flex min-h-full items-center justify-center px-4 py-10 sm:px-8">
        <div className="w-full max-w-2xl animate-fade-up text-center">
          <div className="mx-auto grid size-14 place-items-center rounded-2xl bg-gradient-to-br from-indigo-600 to-violet-600 text-white shadow-lg shadow-indigo-200">
            <SparklesIcon className="size-6" />
          </div>
          <p className="mt-5 text-xs font-semibold uppercase tracking-[0.22em] text-indigo-600">
            {COURSE_META[course].label} Tutor
          </p>
          <h2 className="mt-2 text-balance text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl">
            从课程资料出发，把问题讲明白
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-slate-500">
            我会结合当前课程，通过 AI 助手用中文分步讲解，并展示可用的资料引用。
          </p>
          <div className="mt-8 grid gap-2 text-left sm:grid-cols-2">
            {examples.map((question) => (
              <button
                key={question}
                type="button"
                onClick={() => onExample(question)}
                className="group rounded-2xl border border-slate-200 bg-white p-4 text-sm leading-5 text-slate-700 shadow-sm transition hover:-translate-y-0.5 hover:border-indigo-200 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
              >
                <span className="flex items-start gap-2">
                  <span className="mt-0.5 text-indigo-400 transition group-hover:text-indigo-600" aria-hidden="true">→</span>
                  {question}
                </span>
              </button>
            ))}
          </div>
          <p className="mt-6 text-xs text-slate-400">AI 助手结合当前课程资料回答，资料不足时会如实说明。</p>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-4xl space-y-6 px-4 py-6 sm:px-8 sm:py-8" aria-live="polite">
      {messages.map((message) => (
        <ChatMessage key={message.id} message={message} />
      ))}
      {isLoading && <ThinkingIndicator />}
      <div ref={bottomRef} className="h-px" />
    </div>
  );
}
