"use client";

import { useEffect, useRef } from "react";
import ChatMessage from "@/components/ChatMessage";
import { SparklesIcon } from "@/components/Icons";
import type { ChatMessage as ChatMessageType } from "@/lib/types";

interface ChatWindowProps {
  messages: ChatMessageType[];
  examples: { title: string; question: string }[];
  isLoading: boolean;
  onExample: (question: string) => void;
}

function ThinkingIndicator() {
  return (
    <div className="flex animate-fade-up items-start gap-3" role="status" aria-label="正在整理回答">
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
          <span className="text-sm text-slate-500">正在思考你的问题…</span>
        </div>
      </div>
    </div>
  );
}

export default function ChatWindow({
  messages,
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
      <div className="flex min-h-full items-center justify-center px-5 py-8 sm:px-8 sm:py-12">
        <div className="w-full max-w-2xl animate-fade-up">
          <div className="grid size-12 place-items-center rounded-2xl bg-indigo-50 text-indigo-600">
            <SparklesIcon className="size-6" />
          </div>
          <h2 className="mt-6 text-balance text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl">
            有什么想聊的？
          </h2>
          <p className="mt-3 max-w-xl text-sm leading-7 text-slate-500">
            从一个问题开始，一起理解概念、拆解难题、探索思路。
          </p>
          <div className="mt-8 grid gap-3 text-left sm:grid-cols-2">
            {examples.map(({ title, question }) => (
              <button
                key={question}
                type="button"
                onClick={() => onExample(question)}
                className="group rounded-xl border border-slate-200/80 bg-white p-4 text-left text-sm leading-6 transition hover:border-indigo-300 hover:bg-indigo-50/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
              >
                <span className="block text-xs font-medium text-slate-400">{title}</span>
                <span className="mt-1 block text-slate-700">{question}<span className="ml-2 inline-block text-indigo-400" aria-hidden="true">↗</span></span>
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-3xl space-y-8 px-4 py-7 sm:px-6 sm:py-9" aria-live="polite">
      {messages.map((message) => (
        <ChatMessage key={message.id} message={message} />
      ))}
      {isLoading && <ThinkingIndicator />}
      <div ref={bottomRef} className="h-px" />
    </div>
  );
}
