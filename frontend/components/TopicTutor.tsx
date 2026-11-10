"use client";

import { useEffect, useRef, useState } from "react";
import { AlertIcon, PlayIcon, SparklesIcon } from "@/components/Icons";
import MarkdownRenderer from "@/components/MarkdownRenderer";
import SourcePanel from "@/components/SourcePanel";
import { useStudent } from "@/components/StudentProvider";
import { sendChat } from "@/lib/api";
import { COURSE_META, type ChatHistoryItem, type ChatResponse, type Course } from "@/lib/types";

type Clarification = { question: string; response: ChatResponse };

function Answer({ response }: { response: ChatResponse }) {
  return <>
    <MarkdownRenderer content={response.answer} />
    {Boolean(response.sources?.length) && <details className="mt-6 border-t border-slate-100 pt-4"><summary className="w-fit cursor-pointer text-xs text-slate-500 hover:text-indigo-600">查看 {response.sources.length} 条资料来源</summary><div className="mt-3"><SourcePanel sources={response.sources} /></div></details>}
  </>;
}

export default function TopicTutor({
  course,
  topicId,
  topicTitle,
  disabled = false,
  onLearningStarted,
  onPractice,
}: {
  course: Course;
  topicId: string;
  topicTitle: string;
  disabled?: boolean;
  onLearningStarted?: () => void;
  onPractice: () => void;
}) {
  const { withStudent } = useStudent();
  const startMessage = `当前课程是${COURSE_META[course].label}，我要开始学习${topicTitle}`;
  const [lesson, setLesson] = useState<ChatResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [clarifications, setClarifications] = useState<Clarification[]>([]);
  const [asking, setAsking] = useState(false);
  const [question, setQuestion] = useState("");
  const [questionError, setQuestionError] = useState<string | null>(null);
  const questionDialog = useRef<HTMLDialogElement>(null);
  const latestAnswer = useRef<HTMLElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  useEffect(() => { if (disabled) abortRef.current?.abort(); }, [disabled]);
  useEffect(() => () => abortRef.current?.abort(), []);
  useEffect(() => {
    const dialog = questionDialog.current;
    if (asking && dialog && !dialog.open) dialog.showModal();
    else if (!asking && dialog?.open) dialog.close();
  }, [asking]);
  useEffect(() => {
    if (clarifications.length) latestAnswer.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [clarifications.length]);

  function closeQuestion() {
    abortRef.current?.abort();
    setAsking(false);
  }

  async function clarify() {
    if (!lesson || !question.trim() || abortRef.current || disabled) return;
    const message = `我没看懂：${question.trim()}`;
    const history: ChatHistoryItem[] = [
      { role: "user", content: startMessage },
      { role: "assistant", content: lesson.answer },
      ...clarifications.flatMap<ChatHistoryItem>((turn) => [
        { role: "user", content: `我没看懂：${turn.question}` },
        { role: "assistant", content: turn.response.answer },
      ]),
    ];
    const controller = new AbortController();
    abortRef.current = controller;
    setQuestionError(null);
    setLoading(true);
    try {
      const response = await withStudent((studentId) => sendChat({
        course, topic_id: topicId, learning_mode: "topic_clarification", message,
        history: history.slice(-8).map((item) => ({ ...item, content: item.content.slice(0, 20_000) })),
      }, controller.signal, studentId));
      if (controller.signal.aborted) return;
      setClarifications((turns) => [...turns, { question: question.trim(), response }]);
      setQuestion("");
      setAsking(false);
    } catch (cause) {
      if (!controller.signal.aborted) setQuestionError(cause instanceof Error ? cause.message : "补充讲解暂时无法生成，请重试。");
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
        setLoading(false);
      }
    }
  }

  async function startLearning() {
    if (abortRef.current || loading || disabled || lesson) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setError(null);
    setLoading(true);
    try {
      const response = await withStudent((studentId) => sendChat({
        course,
        topic_id: topicId,
        learning_mode: "topic_teaching",
        message: startMessage,
        history: [],
      }, controller.signal, studentId));
      if (controller.signal.aborted) return;
      setLesson(response);
      onLearningStarted?.();
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "讲解暂时无法生成，请重试。");
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
        setLoading(false);
      }
    }
  }

  return (
    <section id="topic-tutor" aria-label="知识点学习" aria-busy={loading} className="flex min-h-0 flex-1 flex-col bg-white">
      <div className="chat-scrollbar min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 sm:px-8">
        {lesson ? (
          <div className="mx-auto w-full max-w-3xl py-8 sm:py-10">
            <article aria-label="知识点讲解">
              <p className="mb-5 flex items-center gap-2 text-xs font-semibold text-indigo-600"><SparklesIcon className="size-4" />Course Coach</p>
              <Answer response={lesson} />
            </article>
            {clarifications.map((turn, index) => <article key={index} ref={index === clarifications.length - 1 ? latestAnswer : undefined} aria-label="补充讲解" className="mt-8 border-t border-slate-100 pt-6">
              <p className="mb-5 whitespace-pre-wrap break-words rounded-xl bg-slate-50 px-4 py-3 text-sm leading-7 text-slate-600">{turn.question}</p>
              <p className="mb-5 flex items-center gap-2 text-xs font-semibold text-indigo-600"><SparklesIcon className="size-4" />Course Coach</p>
              <Answer response={turn.response} />
            </article>)}
            <div role="group" aria-label="接下来怎么学" className="mt-8 border-t border-slate-100 pt-6">
              <p className="mb-3 text-sm text-slate-500">接下来，你想怎么学？</p>
              <div className="flex flex-wrap gap-3">
                <button type="button" disabled={disabled || loading} onClick={() => { setQuestionError(null); setAsking(true); }} className="rounded-xl border border-slate-200 px-5 py-2.5 text-sm font-medium text-slate-600 hover:border-indigo-300 hover:text-indigo-600 disabled:cursor-not-allowed disabled:opacity-40">没看懂</button>
                <button type="button" disabled={disabled || loading} onClick={onPractice} className="rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-40">做练习</button>
              </div>
              {disabled && <p role="status" className="mt-3 text-xs text-amber-700">测试进行中，请先提交答案，再继续讲解或练习。</p>}
            </div>
          </div>
        ) : (
          <div className="mx-auto flex min-h-full max-w-lg flex-col items-center justify-center py-10 text-center">
            <SparklesIcon className="size-8 text-indigo-500" />
            <h2 className="mt-5 text-xl font-semibold text-slate-900 sm:text-2xl">学习{topicTitle}</h2>
            <p className="mt-3 text-sm leading-7 text-slate-500">点击开始学习，课程助手将为你讲解这个知识点。</p>
            {error && <div role="alert" className="mt-5 flex items-start gap-2 text-left text-sm text-rose-700"><AlertIcon className="mt-0.5 size-4 shrink-0" /><span>{error}</span></div>}
            {loading ? (
              <div className="mt-7">
                <p role="status" className="flex items-center justify-center gap-2 text-sm text-slate-500"><span className="size-2 animate-pulse rounded-full bg-indigo-500" />正在生成知识点讲解…</p>
                <button type="button" onClick={() => abortRef.current?.abort()} className="mt-4 text-xs text-slate-400 hover:text-slate-700">停止生成</button>
              </div>
            ) : <button type="button" onClick={() => void startLearning()} disabled={disabled} className="mt-7 inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-6 py-3 text-sm font-semibold text-white transition hover:bg-indigo-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-40"><PlayIcon className="size-4" />开始学习</button>}
            {disabled && <p role="status" className="mt-4 text-xs leading-6 text-amber-700">测试进行中，请先独立作答。提交后可开始讲解。</p>}
          </div>
        )}
      </div>
      {lesson && <dialog ref={questionDialog} aria-labelledby="clarification-title" onCancel={(event) => { event.preventDefault(); closeQuestion(); }} className="m-auto w-[calc(100%-2rem)] max-w-lg rounded-2xl border-0 bg-white p-0 text-slate-900 shadow-xl backdrop:bg-slate-950/30">
        <form onSubmit={(event) => { event.preventDefault(); void clarify(); }} className="max-h-[85dvh] space-y-5 overflow-y-auto p-5 sm:p-6">
          <h2 id="clarification-title" className="text-lg font-semibold">哪里没看懂？</h2>
          <label className="block text-sm text-slate-500" htmlFor="clarification-question">说说你的疑问，让课程助手再讲一讲。</label>
          <textarea id="clarification-question" autoFocus required maxLength={2000} rows={5} value={question} onChange={(event) => setQuestion(event.target.value)} disabled={loading || disabled} placeholder="例如：能再解释一下训练数据和标签的关系吗？" className="w-full resize-y rounded-xl border border-slate-200 p-3 text-sm leading-7 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-50" />
          {questionError && <p role="alert" className="text-sm text-rose-700">{questionError}</p>}
          {loading && <p role="status" className="text-sm text-indigo-600">正在生成补充讲解…</p>}
          {disabled && <p role="status" className="text-sm text-amber-700">请先完成当前测试。</p>}
          <div className="flex justify-end gap-3">
            <button type="button" onClick={closeQuestion} className="rounded-xl px-4 py-2.5 text-sm text-slate-500 hover:bg-slate-50">{loading ? "停止并关闭" : "取消"}</button>
            <button type="submit" disabled={!question.trim() || loading || disabled} className="rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-40">继续讲解</button>
          </div>
        </form>
      </dialog>}
    </section>
  );
}
