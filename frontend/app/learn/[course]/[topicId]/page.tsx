"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { useCourseOutline } from "@/components/CourseLayout";
import { LoadingBlock, MasteryBar, TopicStatusBadge } from "@/components/LearningWidgets";
import LessonContent, { WorkedExample } from "@/components/LessonContent";
import TopicPrerequisiteCard from "@/components/TopicPrerequisiteCard";
import PracticePanel from "@/components/PracticePanel";
import TopicTutor from "@/components/TopicTutor";
import { ArrowLeftIcon, ArrowRightIcon } from "@/components/Icons";
import { useStudent } from "@/components/StudentProvider";
import { ApiError, getLearningHistory, getTopic, isStudentNotFound, startTopic } from "@/lib/api";
import { getExamples, getLesson, getPrerequisites } from "@/lib/api-content";
import { hasValidTopicEvidence, scoreLabel } from "@/lib/learning";
import { COURSE_META, COURSES, type Course, type CurriculumTopic, type RecentLearningAttempt } from "@/lib/types";
import type { Assessment, Lesson, Prerequisites, WorkedExampleData } from "@/lib/types-content";

export default function TopicLearningPage() {
  const params = useParams<{ course: string; topicId: string }>();
  return <TopicContent key={`${params.course}:${params.topicId}`} ownerCourse={params.course as Course} topicId={decodeURIComponent(params.topicId)} />;
}

function TopicContent({ ownerCourse, topicId }: { ownerCourse: Course; topicId: string }) {
  const { withStudent, status } = useStudent();
  const { outline, course, topicHref, refresh } = useCourseOutline();
  const searchParams = useSearchParams();
  const [topic, setTopic] = useState<CurriculumTopic | null>(null);
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [examples, setExamples] = useState<WorkedExampleData[]>([]);
  const [prerequisites, setPrerequisites] = useState<Prerequisites | null>(null);
  const [history, setHistory] = useState<RecentLearningAttempt[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [contentError, setContentError] = useState("");
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [formalActive, setFormalActive] = useState(false);
  const [practiceRequest, setPracticeRequest] = useState(0);
  const [panel, setPanel] = useState<"info" | "practice" | "history" | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = dialogRef.current;
    if (panel && dialog && !dialog.open) dialog.showModal();
    else if (!panel && dialog?.open) dialog.close();
  }, [panel]);
  const load = useCallback(async () => {
    setError("");
    setPrerequisites(null);
    try {
      const values = await withStudent(async (id) => {
        const results = await Promise.allSettled([
          getTopic(topicId, id), getPrerequisites(topicId, id), getLesson(topicId), getExamples(topicId), getLearningHistory(ownerCourse, id),
        ]);
        // Preserve the provider's single retry when one request finds a stale identity.
        for (const result of results) if (result.status === "rejected" && isStudentNotFound(result.reason)) throw result.reason;
        return results;
      });
      if (values[0].status === "rejected") throw values[0].reason;
      if (values[0].value.course !== ownerCourse) throw new Error("该地址与知识点归属不一致，请从课程目录重新进入。");
      setTopic(values[0].value);
      if (values[1].status === "fulfilled") setPrerequisites(values[1].value);
      else {
        const cause = values[1].reason;
        const details = cause instanceof ApiError ? `${cause.message}${cause.code && /^[A-Z0-9_]{1,80}$/i.test(cause.code) ? `（${cause.code}）` : ""}` : "无法完成前置能力检查。";
        setError(`前置能力检查暂时不可用：${details} 正式测试暂不开放。请重试；讲解和例题仍可阅读。`);
      }
      if (values[2].status === "fulfilled") { setLesson(values[2].value); setContentError(""); }
      else if (values[2].reason instanceof ApiError && values[2].reason.status === 404) { setLesson(null); setContentError(""); }
      else setContentError("课程正文暂时加载失败，请重新加载内容。");
      if (values[3].status === "fulfilled") setExamples(values[3].value.examples);
      else setContentError("例题暂时加载失败，请重新加载内容。");
      if (values[4].status === "fulfilled") setHistory(values[4].value.events.filter((event) => event.topic_id === topicId));
    } catch (cause) { setError(cause instanceof Error ? cause.message : "知识点暂时无法加载，请重试。"); }
    finally { setLoading(false); }
  }, [topicId, ownerCourse, withStudent]);
  useEffect(() => { if (status !== "ready") return; const timer = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(timer); }, [status, load]);
  const onLearningUpdated = useCallback(async () => { await Promise.all([load(), refresh()]); }, [load, refresh]);
  async function recordLearning() {
    if (topic?.status !== "not_started") return;
    try { await withStudent((id) => startTopic(topicId, id)); await onLearningUpdated(); }
    catch { setError("学习状态暂时未能保存，可以继续对话，稍后重试。"); }
  }
  if (!COURSES.includes(ownerCourse)) return <div className="p-8"><h1>课程地址无效</h1><Link href="/learn" className="text-indigo-700">返回课程列表</Link></div>;
  if (loading) return <div className="p-5 sm:p-8"><LoadingBlock label="正在准备课程对话…" /></div>;
  if (!topic) return <div role="alert" className="m-5 rounded-2xl bg-rose-50 p-6 text-rose-800"><h1 className="font-bold">知识点无法加载</h1><p className="mt-2 text-sm">{error}</p><button type="button" onClick={() => void load()} className="mt-4 underline">重新加载</button></div>;
  const ordered = outline?.groups.flatMap((group) => group.topics) ?? [];
  const position = ordered.findIndex((item) => item.topic_id === topicId);
  const previous = position > 0 ? ordered[position - 1] : null;
  const next = position >= 0 ? ordered[position + 1] : null;
  const returnTopic = searchParams.get("return_topic");
  const panelTitle = panel === "info" ? "知识点资料" : panel === "practice" ? "练习与测试" : "学习记录";
  return <div className="flex h-[calc(100dvh-120px)] min-h-0 flex-col bg-white lg:h-[calc(100dvh-65px)]">
    <header className="shrink-0 border-b border-slate-100 px-4 py-3 sm:px-6">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-[11px] text-slate-400">{COURSE_META[ownerCourse].label}{course && course !== ownerCourse ? ` · 从${COURSE_META[course].label}补学` : ""}</p>
          <div className="mt-1 flex min-w-0 items-center gap-3"><h1 className="truncate text-base font-semibold text-slate-900">{topic.title}</h1><span className="hidden shrink-0 sm:inline"><TopicStatusBadge status={topic.status} /></span></div>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <nav aria-label="学习工具" className="flex items-center gap-1">
          {([["info", "知识点资料"], ["practice", "练习与测试"], ["history", "学习记录"]] as const).map(([id, label]) => <button key={id} type="button" onClick={() => setPanel(id)} className="rounded-lg px-2 py-1.5 text-xs text-slate-500 transition hover:bg-slate-50 hover:text-indigo-600">{label}{id === "practice" && formalActive && <span className="ml-1.5 inline-block size-1.5 rounded-full bg-amber-500" />}</button>)}
        </nav>
        <div className="flex items-center gap-1">
          {course && course !== ownerCourse && <Link href={returnTopic ? `/learn/${course}/${encodeURIComponent(returnTopic)}` : `/learn/${course}`} className="mr-2 text-xs text-indigo-600">返回原课程</Link>}
          {previous && <Link href={topicHref(previous)} prefetch={false} aria-label={`上一个：${previous.title}`} title={`上一个：${previous.title}`} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-50 hover:text-slate-700"><ArrowLeftIcon className="size-4" /></Link>}
          {next && <Link href={topicHref(next)} prefetch={false} aria-label={`下一个：${next.title}`} title={`下一个：${next.title}`} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-50 hover:text-slate-700"><ArrowRightIcon className="size-4" /></Link>}
        </div>
      </div>
    </header>
    {error && <div role="alert" className="flex shrink-0 items-start gap-3 bg-amber-50 px-5 py-2 text-xs leading-5 text-amber-800"><span className="flex-1">{error}</span><button type="button" onClick={() => void load()} className="shrink-0 underline">重试</button></div>}
    <TopicTutor key={topic.id} course={ownerCourse} topicId={topic.id} topicTitle={topic.title} disabled={formalActive} onLearningStarted={() => void recordLearning()} onPractice={() => { setAssessment(null); setPanel("practice"); setPracticeRequest((value) => value + 1); }} />

    <dialog ref={dialogRef} onCancel={(event) => { event.preventDefault(); setPanel(null); }} aria-label={panelTitle} className="fixed inset-y-0 left-auto right-0 m-0 ml-auto h-dvh max-h-dvh w-full max-w-2xl border-0 bg-white p-0 text-slate-900 shadow-2xl backdrop:bg-slate-950/30"
      onClick={(event) => { if (event.target instanceof Element && event.target.closest('a[href="#practice"]')) { event.preventDefault(); setPanel("practice"); return; } if (event.target !== event.currentTarget) return; const bounds = event.currentTarget.getBoundingClientRect(); if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) setPanel(null); }}>
      <div className="flex h-full min-h-0 flex-col">
        <div className="flex shrink-0 items-center justify-between border-b border-slate-200 px-5 py-4"><h2 className="text-base font-semibold">{panelTitle}</h2><button type="button" onClick={() => setPanel(null)} aria-label="关闭学习工具" className="rounded-lg px-3 py-1 text-lg text-slate-500 hover:bg-slate-100">×</button></div>
        <div className="chat-scrollbar min-h-0 flex-1 overflow-y-auto overscroll-contain p-4 sm:p-6">
          <div hidden={panel !== "info"} className="space-y-5">
            <section><h3 className="text-sm font-semibold">{topic.title}</h3><p className="mt-2 text-sm leading-7 text-slate-500">{topic.description}</p><h3 className="mt-5 text-sm font-semibold">学习目标</h3><ul className="mt-2 list-disc space-y-2 pl-5 text-sm leading-6 text-slate-600">{topic.learning_objectives.map((objective) => <li key={objective}>{objective}</li>)}</ul></section>
            {contentError && <p role="alert" className="text-sm text-rose-700">{contentError}<button type="button" onClick={() => void load()} className="ml-2 underline">重试</button></p>}
            {prerequisites && <TopicPrerequisiteCard data={prerequisites} onAssessment={(value) => { setAssessment(value); setPanel("practice"); }} />}
            {lesson && <LessonContent lesson={lesson} />}
            {examples.map((example) => <WorkedExample key={`${example.id}:${example.version}`} example={example} askDisabled={formalActive} />)}
            {prerequisites && prerequisites.successors.length > 0 && <section><h3 className="text-sm font-semibold">后续知识点</h3><div className="mt-3 flex flex-wrap gap-3">{prerequisites.successors.map((item) => <Link key={item.id} href={topicHref({ topic_id: item.id, owner_course: item.course })} className="text-sm text-indigo-600">{item.title} →</Link>)}</div></section>}
          </div>
          <div hidden={panel !== "practice"} className="space-y-5">
            {prerequisites && prerequisites.unmet.length > 0 && <button type="button" onClick={() => setPanel("info")} className="text-sm font-semibold text-indigo-600">查看前置学习与前置小测 →</button>}
            <PracticePanel topic={topic} checkpointAllowed={prerequisites?.can_checkpoint ?? false} checkpointBlockedReason={!prerequisites ? "前置能力状态尚未确认，请重试检查。" : prerequisites.unmet.length ? "请先完成前置学习，或通过前置小测。" : "先完成练习并积累学习证据，再参加综合验收。"} initialAssessment={assessment} generationRequest={practiceRequest} onLearningUpdated={onLearningUpdated} onActiveCheckpoint={setFormalActive} />
          </div>
          <div hidden={panel !== "history"}>
            <div className="max-w-md"><MasteryBar value={hasValidTopicEvidence(topic) ? topic.mastery : null} /></div>
            {history.length ? <ul className="mt-5 divide-y divide-slate-100">{history.map((event, index) => <li key={event.id || event.attempt_id || index} className="flex flex-wrap justify-between gap-2 py-4 text-sm text-slate-600"><span>{event.mode === "checkpoint" ? "综合验收" : "练习"} · {scoreLabel(event.score)}</span><time className="text-xs text-slate-400">{new Date(event.created_at).toLocaleString("zh-CN")}</time></li>)}</ul> : <p className="mt-6 text-sm text-slate-400">完成练习后，可以在这里查看成绩与学习记录。</p>}
          </div>
        </div>
      </div>
    </dialog>
  </div>;
}
