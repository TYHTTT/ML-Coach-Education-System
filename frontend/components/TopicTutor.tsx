"use client";

import { useEffect, useRef } from "react";
import { AlertIcon, PlayIcon, SparklesIcon } from "@/components/Icons";
import MarkdownRenderer from "@/components/MarkdownRenderer";
import SourcePanel from "@/components/SourcePanel";
import { useStudent } from "@/components/StudentProvider";
import { useTopicConversation } from "@/components/TopicSessionsProvider";
import { ApiError, sendChat } from "@/lib/api";
import { splitPracticeContent } from "@/lib/practice-content";
import { type ChatHistoryItem, type Course } from "@/lib/types";
import { useCourseCatalog } from "@/components/CourseCatalogProvider";
import type {
  TopicAction as Action,
  TopicInputMode as InputMode,
} from "@/lib/topic-chat-storage";

const ANSWER_LABELS: Record<Action, string> = {
  topic_teaching: "知识点讲解",
  topic_clarification: "补充讲解",
  topic_practice: "练习题",
  topic_answer: "作答反馈",
};
const LOADING_LABELS: Record<Action, string> = {
  topic_teaching: "正在生成知识点讲解…",
  topic_clarification: "正在生成补充讲解…",
  topic_practice: "正在出题…",
  topic_answer: "正在评价答案…",
};

export default function TopicTutor({
  course,
  topicId,
  topicTitle,
  onLearningStarted,
}: {
  course: Course;
  topicId: string;
  topicTitle: string;
  onLearningStarted?: () => void;
}) {
  const { withStudent } = useStudent();
  const { courses } = useCourseCatalog();
  const courseName =
    courses.find((item) => item.id === course)?.title ?? course;
  const startMessage = `当前课程是${courseName}，我要开始学习${topicTitle}`;
  const { state, update, begin, finish, stop, rememberPath, storageError } =
    useTopicConversation(course, topicId);
  const { turns, pending, failure, inputMode, drafts, awaitingAnswer } = state;
  const latestAnswer = useRef<HTMLElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const inputPanel = useRef<HTMLFormElement>(null);
  const activityRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    rememberPath(window.location.pathname + window.location.search);
  }, [rememberPath, course, topicId]);
  useEffect(() => {
    if (turns.length)
      latestAnswer.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
  }, [turns.length]);
  useEffect(() => {
    if (inputMode) inputRef.current?.focus({ preventScroll: true });
  }, [inputMode]);
  useEffect(() => {
    if (pending || failure)
      activityRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
      });
  }, [pending, failure]);

  function openInput(mode: InputMode) {
    update((current) => ({ ...current, inputMode: mode, failure: null }));
    window.requestAnimationFrame(() =>
      inputPanel.current?.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
      }),
    );
  }

  async function requestAnswer(action: Action, message: string) {
    const controller = begin();
    if (!controller) return;
    const starting = action === "topic_teaching";
    const token = starting
      ? undefined
      : turns.at(-1)?.response.conversation_token;
    const history: ChatHistoryItem[] =
      starting || token
        ? []
        : turns
            .flatMap<ChatHistoryItem>((turn) => [
              { role: "user", content: turn.message },
              { role: "assistant", content: turn.response.answer },
            ])
            .slice(-8)
            .map((item) => ({
              ...item,
              content: item.content.slice(0, 20_000),
            }));
    update((current) => ({
      ...current,
      pending: action,
      pendingMessage: message,
      failure: null,
    }));
    try {
      const response = await withStudent((studentId) =>
        sendChat(
          {
            course,
            topic_id: topicId,
            learning_mode: action,
            message,
            history,
            ...(token ? { conversation_token: token } : {}),
          },
          controller.signal,
          studentId,
        ),
      );
      if (controller.signal.aborted) return;
      if (
        action === "topic_practice" &&
        !splitPracticeContent(response.answer).question
      ) {
        throw new Error("Agent 没有返回可单独展示的题目，请重试出题。");
      }
      const turn = { action, message, response };
      update((current) => ({
        ...current,
        turns: starting ? [turn] : [...current.turns, turn],
        drafts: starting
          ? { clarification: "", answer: "" }
          : {
              clarification:
                action === "topic_clarification"
                  ? ""
                  : current.drafts.clarification,
              answer: action === "topic_answer" ? "" : current.drafts.answer,
            },
        awaitingAnswer:
          starting || action === "topic_answer"
            ? false
            : action === "topic_practice" || current.awaitingAnswer,
        inputMode:
          starting || action === "topic_answer"
            ? null
            : action === "topic_practice" || current.awaitingAnswer
              ? "answer"
              : null,
      }));
      if (starting) onLearningStarted?.();
    } catch (cause) {
      if (!controller.signal.aborted)
        update((current) => ({
          ...current,
          failure: {
            action,
            message,
            error:
              cause instanceof Error
                ? cause.message
                : "课程助手暂时无法回复，请重试。",
            expired: cause instanceof ApiError && cause.status === 403,
          },
        }));
    } finally {
      finish(controller);
    }
  }

  function practice() {
    if (awaitingAnswer) {
      openInput("answer");
      return;
    }
    void requestAnswer(
      "topic_practice",
      `当前课程是${courseName}，我要做${topicTitle}的练习。请只出题，不要给答案或解析，等我提交答案后再评价。`,
    );
  }

  return (
    <section
      id="topic-tutor"
      aria-label="知识点学习"
      aria-busy={Boolean(pending)}
      className="flex min-h-0 flex-1 flex-col bg-white"
    >
      {storageError && (
        <p
          role="alert"
          className="bg-amber-50 px-5 py-2 text-xs text-amber-800"
        >
          当前浏览器无法保存学习对话，切换页面仍可继续，刷新前请留存内容。
        </p>
      )}
      <div className="chat-scrollbar min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 sm:px-8">
        {turns.length ? (
          <div className="mx-auto w-full max-w-3xl py-8 sm:py-10">
            {turns.map((turn, index) => {
              const practice =
                turn.action === "topic_practice"
                  ? splitPracticeContent(turn.response.answer)
                  : null;
              const submitted =
                practice &&
                turns
                  .slice(index + 1)
                  .find(
                    (next) =>
                      next.action === "topic_answer" ||
                      next.action === "topic_practice",
                  )?.action === "topic_answer";
              return (
                <article
                  key={index}
                  ref={index === turns.length - 1 ? latestAnswer : undefined}
                  aria-label={ANSWER_LABELS[turn.action]}
                  className={index ? "mt-8 border-t border-slate-100 pt-6" : ""}
                >
                  {(turn.action === "topic_clarification" ||
                    turn.action === "topic_answer") && (
                    <p className="mb-5 whitespace-pre-wrap break-words rounded-xl bg-slate-50 px-4 py-3 text-sm leading-7 text-slate-600">
                      {turn.message.replace(
                        /^(?:我没看懂|我的答案是)[：:]/,
                        "",
                      )}
                    </p>
                  )}
                  <p className="mb-5 flex items-center gap-2 text-xs font-semibold text-indigo-600">
                    <SparklesIcon className="size-4" />
                    Course Coach
                  </p>
                  <MarkdownRenderer
                    content={practice?.question ?? turn.response.answer}
                  />
                  {practice?.reference && submitted && (
                    <details
                      aria-label="练习参考答案"
                      className="mt-6 border-t border-slate-100 pt-4"
                    >
                      <summary className="w-fit cursor-pointer text-sm font-medium text-indigo-600">
                        查看参考答案与解析
                      </summary>
                      <div className="mt-3">
                        <MarkdownRenderer content={practice.reference} />
                      </div>
                    </details>
                  )}
                  {(!practice || submitted) &&
                    Boolean(turn.response.sources?.length) && (
                      <details className="mt-6 border-t border-slate-100 pt-4">
                        <summary className="w-fit cursor-pointer text-xs text-slate-500 hover:text-indigo-600">
                          查看 {turn.response.sources.length} 条资料来源
                        </summary>
                        <div className="mt-3">
                          <SourcePanel sources={turn.response.sources} />
                        </div>
                      </details>
                    )}
                </article>
              );
            })}
            {(failure || pending) && (
              <div ref={activityRef} className="mt-6">
                {failure && (
                  <div
                    role="alert"
                    className="rounded-xl bg-rose-50 p-4 text-sm text-rose-700"
                  >
                    <p>{failure.error}</p>
                    {(failure.expired || !inputMode) && (
                      <button
                        type="button"
                        disabled={Boolean(pending)}
                        onClick={() =>
                          void requestAnswer(
                            failure.expired ? "topic_teaching" : failure.action,
                            failure.expired ? startMessage : failure.message,
                          )
                        }
                        className="mt-2 font-semibold underline disabled:opacity-40"
                      >
                        {failure.expired ? "重新开始学习" : "重试"}
                      </button>
                    )}
                  </div>
                )}
                {pending && (
                  <article
                    aria-label="等待课程助手回复"
                    className="border-t border-slate-100 pt-6"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <p
                        role="status"
                        aria-live="polite"
                        className="flex items-center gap-2 text-sm text-indigo-600"
                      >
                        <span className="size-2 animate-pulse rounded-full bg-indigo-500" />
                        {LOADING_LABELS[pending]}
                      </p>
                      <button
                        type="button"
                        onClick={stop}
                        className="text-xs text-slate-500 hover:text-slate-800"
                      >
                        停止生成
                      </button>
                    </div>
                  </article>
                )}
              </div>
            )}
            {inputMode ? (
              <form
                ref={inputPanel}
                aria-label={inputMode === "answer" ? "练习作答" : "追问"}
                onSubmit={(event) => {
                  event.preventDefault();
                  const text = drafts[inputMode].trim();
                  if (text)
                    void requestAnswer(
                      inputMode === "answer"
                        ? "topic_answer"
                        : "topic_clarification",
                      `${inputMode === "answer" ? "我的答案是" : "我没看懂"}：${text}`,
                    );
                }}
                className="mt-7 space-y-3 border-t border-slate-100 pt-6"
              >
                <label
                  htmlFor="topic-response"
                  className="block text-sm font-semibold text-slate-700"
                >
                  {inputMode === "answer" ? "你的答案" : "哪里没看懂？"}
                </label>
                <textarea
                  ref={inputRef}
                  id="topic-response"
                  required
                  maxLength={6000}
                  rows={4}
                  value={drafts[inputMode]}
                  onChange={(event) =>
                    update((current) => ({
                      ...current,
                      drafts: {
                        ...current.drafts,
                        [inputMode]: event.target.value,
                      },
                    }))
                  }
                  disabled={Boolean(pending)}
                  placeholder={
                    inputMode === "answer"
                      ? "在这里写下答案，多道题可按题号分别作答…"
                      : "说说你的疑问，让课程助手再讲一讲…"
                  }
                  className="w-full resize-y rounded-xl border border-slate-200 p-3 text-sm leading-7 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-50"
                />
                <div className="flex justify-end gap-3">
                  <button
                    type="button"
                    disabled={Boolean(pending)}
                    onClick={() =>
                      update((current) => ({ ...current, inputMode: null }))
                    }
                    className="rounded-xl px-4 py-2.5 text-sm text-slate-500 hover:bg-slate-50 disabled:opacity-40"
                  >
                    收起
                  </button>
                  <button
                    type="submit"
                    disabled={!drafts[inputMode].trim() || Boolean(pending)}
                    className="rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {inputMode === "answer" ? "提交答案" : "继续讲解"}
                  </button>
                </div>
              </form>
            ) : (
              !pending && (
                <div
                  role="group"
                  aria-label="接下来怎么学"
                  className="mt-8 border-t border-slate-100 pt-6"
                >
                  <p className="mb-3 text-sm text-slate-500">
                    接下来，你想怎么学？
                  </p>
                  <div className="flex flex-wrap gap-3">
                    <button
                      type="button"
                      onClick={() => openInput("clarification")}
                      className="rounded-xl border border-slate-200 px-5 py-2.5 text-sm font-medium text-slate-600 hover:border-indigo-300 hover:text-indigo-600"
                    >
                      没看懂
                    </button>
                    <button
                      type="button"
                      onClick={practice}
                      className="rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700"
                    >
                      {awaitingAnswer ? "继续作答" : "做练习"}
                    </button>
                  </div>
                </div>
              )
            )}
          </div>
        ) : (
          <div className="mx-auto flex min-h-full max-w-lg flex-col items-center justify-center py-10 text-center">
            <SparklesIcon className="size-8 text-indigo-500" />
            <h2 className="mt-5 text-xl font-semibold text-slate-900 sm:text-2xl">
              学习{topicTitle}
            </h2>
            <p className="mt-3 text-sm leading-7 text-slate-500">
              点击开始学习，课程助手将为你讲解这个知识点。
            </p>
            {failure && (
              <div
                role="alert"
                className="mt-5 flex items-start gap-2 text-left text-sm text-rose-700"
              >
                <AlertIcon className="mt-0.5 size-4 shrink-0" />
                <span>{failure.error}</span>
              </div>
            )}
            {pending ? (
              <div className="mt-7">
                <p
                  role="status"
                  className="flex items-center justify-center gap-2 text-sm text-slate-500"
                >
                  <span className="size-2 animate-pulse rounded-full bg-indigo-500" />
                  {LOADING_LABELS[pending]}
                </p>
                <button
                  type="button"
                  onClick={stop}
                  className="mt-4 text-xs text-slate-400 hover:text-slate-700"
                >
                  停止生成
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() =>
                  void requestAnswer("topic_teaching", startMessage)
                }
                className="mt-7 inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-6 py-3 text-sm font-semibold text-white transition hover:bg-indigo-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2"
              >
                <PlayIcon className="size-4" />
                开始学习
              </button>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
