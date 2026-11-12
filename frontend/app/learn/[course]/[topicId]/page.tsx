"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useCourseOutline } from "@/components/CourseLayout";
import { LoadingBlock, TopicStatusBadge } from "@/components/LearningWidgets";
import TopicTutor from "@/components/TopicTutor";
import { ArrowLeftIcon, ArrowRightIcon } from "@/components/Icons";
import { useStudent } from "@/components/StudentProvider";
import { getTopic, startTopic } from "@/lib/api";
import type { Course, CurriculumTopic } from "@/lib/types";
import { useCourseCatalog } from "@/components/CourseCatalogProvider";

export default function TopicLearningPage() {
  const params = useParams<{ course: string; topicId: string }>();
  return <TopicContent key={`${params.course}:${params.topicId}`} courseId={params.course as Course} topicId={decodeURIComponent(params.topicId)} />;
}

function TopicContent({ courseId, topicId }: { courseId: Course; topicId: string }) {
  const { withStudent, status } = useStudent();
  const catalog = useCourseCatalog();
  const courseRecord = catalog.courses.find((item) => item.id === courseId);
  const { outline, topicHref, refresh } = useCourseOutline();
  const [topic, setTopic] = useState<CurriculumTopic | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setError("");
    try {
      const value = await withStudent((id) => getTopic(topicId, id));
      if (value.course !== courseId) throw new Error("该地址与知识点归属不一致，请从课程目录重新进入。");
      setTopic(value);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "知识点暂时无法加载，请重试。"); }
    finally { setLoading(false); }
  }, [topicId, courseId, withStudent]);
  useEffect(() => {
    if (status !== "ready" || !courseRecord) return;
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [status, courseId, load, courseRecord]);
  async function recordLearning() {
    if (topic?.status !== "not_started") return;
    try {
      const value = await withStudent((id) => startTopic(topicId, id));
      setTopic(value);
      await refresh();
    } catch { setError("学习状态暂时未能保存，可以继续对话，稍后重试。"); }
  }
  if (catalog.loading) return <div className="p-5"><LoadingBlock label="正在加载课程…" /></div>;
  if (catalog.error) return <div role="alert" className="p-5 text-sm text-rose-700">{catalog.error}<button type="button" onClick={catalog.reload} className="ml-3 underline">重试</button></div>;
  if (!courseRecord) return <div className="p-8"><h1>课程地址无效</h1><Link href="/learn" className="text-indigo-700">返回课程列表</Link></div>;
  if (loading) return <div className="p-5 sm:p-8"><LoadingBlock label="正在准备课程对话…" /></div>;
  if (!topic) return <div role="alert" className="m-5 rounded-2xl bg-rose-50 p-6 text-rose-800"><h1 className="font-bold">知识点无法加载</h1><p className="mt-2 text-sm">{error}</p><button type="button" onClick={() => void load()} className="mt-4 underline">重新加载</button></div>;
  const ordered = outline?.groups.flatMap((group) => group.topics) ?? [];
  const position = ordered.findIndex((item) => item.topic_id === topicId);
  const previous = position > 0 ? ordered[position - 1] : null;
  const next = position >= 0 ? ordered[position + 1] : null;
  return <div className="flex h-[calc(100dvh-120px)] min-h-0 flex-col bg-white lg:h-[calc(100dvh-65px)]">
    <header className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-100 px-4 py-3 sm:px-6">
      <div className="min-w-0">
        <p className="truncate text-[11px] text-slate-400">{courseRecord.title}</p>
        <div className="mt-1 flex min-w-0 items-center gap-3"><h1 className="truncate text-base font-semibold text-slate-900">{topic.title}</h1><span className="hidden shrink-0 sm:inline"><TopicStatusBadge status={topic.status} /></span></div>
      </div>
      <nav aria-label="知识点导航" className="flex shrink-0 items-center gap-1">
        {previous && <Link href={topicHref(previous)} prefetch={false} aria-label={`上一个：${previous.title}`} title={`上一个：${previous.title}`} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-50 hover:text-slate-700"><ArrowLeftIcon className="size-4" /></Link>}
        {next && <Link href={topicHref(next)} prefetch={false} aria-label={`下一个：${next.title}`} title={`下一个：${next.title}`} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-50 hover:text-slate-700"><ArrowRightIcon className="size-4" /></Link>}
      </nav>
    </header>
    {error && <div role="alert" className="flex shrink-0 items-start gap-3 bg-amber-50 px-5 py-2 text-xs leading-5 text-amber-800"><span className="flex-1">{error}</span><button type="button" onClick={() => void load()} className="shrink-0 underline">重试</button></div>}
    <TopicTutor key={topic.id} course={courseId} topicId={topic.id} topicTitle={topic.title} onLearningStarted={() => void recordLearning()} />
  </div>;
}
