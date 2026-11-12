"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertIcon,
  ArrowLeftIcon,
  ArrowRightIcon,
  ChartIcon,
  ClockIcon,
  LayersIcon,
  TargetIcon,
  TrophyIcon,
} from "@/components/Icons";
import { LoadingBlock, MasteryBar, TopicStatusBadge } from "@/components/LearningWidgets";
import { useCourseCatalog } from "@/components/CourseCatalogProvider";
import { useStudent } from "@/components/StudentProvider";
import { getCurriculum, getLearningDashboard } from "@/lib/api";
import { hasValidTopicEvidence, nextActionLabel, scoreLabel } from "@/lib/learning";
import {
  type Course,
  type CurriculumResponse,
  type CurriculumTopicSummary,
  type LearningDashboard,
} from "@/lib/types";

function visibleMastery(topic: CurriculumTopicSummary): number | null {
  return hasValidTopicEvidence(topic) ? topic.mastery : null;
}

function TopicCard({ topic, course }: { topic: CurriculumTopicSummary; course: Course }) {
  const content = (
    <>
      <div className="flex items-start justify-between gap-3">
        <span className="grid size-8 shrink-0 place-items-center rounded-xl bg-slate-100 text-xs font-bold tabular-nums text-slate-500">
          {topic.order_index ?? "·"}
        </span>
        <TopicStatusBadge status={topic.status} />
      </div>
      <h3 className="mt-4 text-sm font-semibold text-slate-900">{topic.title}</h3>
      {topic.description && <p className="mt-1.5 line-clamp-2 text-xs leading-5 text-slate-500">{topic.description}</p>}
      <div className="mt-4">
        <MasteryBar value={visibleMastery(topic)} compact />
      </div>
    </>
  );

  return (
    <Link
      href={`/learn/${course}/${encodeURIComponent(topic.id)}`}
      className="group rounded-2xl border border-slate-200 bg-white p-4 shadow-sm transition hover:-translate-y-0.5 hover:border-indigo-300 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2"
    >
      {content}
      <span className="mt-4 inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-600">
        进入知识点 <ArrowRightIcon className="size-3.5 transition-transform group-hover:translate-x-0.5" />
      </span>
    </Link>
  );
}

export default function CourseDashboardPage() {
  const params = useParams<{ course: string }>();
  const rawCourse = Array.isArray(params.course) ? params.course[0] : params.course;
  const catalog = useCourseCatalog();
  const courseRecord = catalog.courses.find((item) => item.id === rawCourse);
  const course = courseRecord?.id ?? null;
  const { status: studentStatus, withStudent } = useStudent();
  const [dashboard, setDashboard] = useState<LearningDashboard | null>(null);
  const [curriculum, setCurriculum] = useState<CurriculumResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const loadRequest = useRef(0);
  const currentDashboard = dashboard?.course === course ? dashboard : null;
  const currentCurriculum = curriculum?.course === course ? curriculum : null;

  const load = useCallback(async () => {
    if (!course) return;
    const requestId = ++loadRequest.current;
    setLoading(true);
    setError(null);
    try {
      const [nextDashboard, nextCurriculum] = await withStudent((studentId) =>
        Promise.all([
          getLearningDashboard(course, studentId),
          getCurriculum(course, studentId),
        ]),
      );
      if (requestId === loadRequest.current) {
        setDashboard(nextDashboard);
        setCurriculum(nextCurriculum);
      }
    } catch (cause) {
      if (requestId === loadRequest.current) setError(cause instanceof Error ? cause.message : "学习进度加载失败，请稍后重试。");
    } finally {
      if (requestId === loadRequest.current) setLoading(false);
    }
  }, [course, withStudent]);

  useEffect(() => {
    if (studentStatus === "initializing" || !course) return;
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [course, load, studentStatus]);

  const progress = currentDashboard && currentDashboard.total_topics > 0
    ? currentDashboard.mastered_count / currentDashboard.total_topics
    : 0;
  const activeStage = useMemo(() => {
    if (!currentCurriculum) return null;
    return currentCurriculum.stages.find((stage) =>
      stage.topics.some((topic) => !["not_started", "mastered"].includes(topic.status)),
    ) ?? currentCurriculum.stages.find((stage) => stage.topics.some((topic) => topic.status !== "mastered")) ?? null;
  }, [currentCurriculum]);

  if (catalog.loading) return <div className="p-8"><LoadingBlock label="正在加载课程…" /></div>;
  if (catalog.error) return <div role="alert" className="p-8 text-sm text-rose-700">{catalog.error}<button type="button" onClick={catalog.reload} className="ml-3 underline">重试</button></div>;
  if (!course) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16 text-center sm:px-6">
        <AlertIcon className="mx-auto size-9 text-amber-500" />
        <h1 className="mt-4 text-xl font-bold text-slate-900">课程不存在</h1>
        <Link href="/learn" className="mt-5 inline-flex rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white">返回课程列表</Link>
      </div>
    );
  }

  const meta = { label: courseRecord?.title ?? course, shortLabel: (courseRecord?.title ?? course).slice(0, 2) };
  const recommended = currentDashboard
    ? currentCurriculum?.stages
        .flatMap((stage) => stage.topics)
        .find((topic) => topic.id === currentDashboard.recommended_topic_id) ?? currentDashboard.current_topic
    : null;

  return (
    <div className="min-h-[calc(100svh-65px)] bg-canvas">
      <div className="mx-auto max-w-7xl px-4 py-7 sm:px-6 sm:py-10 lg:px-8">
        <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-end">
          <div>
            <Link href="/learn" className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 transition hover:text-indigo-700">
              <ArrowLeftIcon className="size-3.5" /> 切换课程
            </Link>
            <div className="mt-4 flex items-center gap-4">
              <span className={`grid size-12 place-items-center rounded-2xl text-lg font-bold text-white shadow-lg ${course === "machine_learning" ? "bg-gradient-to-br from-indigo-600 to-violet-600" : "bg-gradient-to-br from-cyan-600 to-sky-600"}`}>
                {meta.shortLabel}
              </span>
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.16em] text-indigo-600">Learning Dashboard</p>
                <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-950 sm:text-3xl">{meta.label}学习路径</h1>
              </div>
            </div>
          </div>
          <Link href="/?view=chat" className="inline-flex w-fit items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-600 shadow-sm transition hover:border-indigo-200 hover:text-indigo-700">
            自由问答 <ArrowRightIcon className="size-4" />
          </Link>
        </div>

        {loading || studentStatus === "initializing" ? (
          <div className="mt-7"><LoadingBlock /></div>
        ) : error ? (
          <div className="mt-7 rounded-3xl border border-rose-200 bg-rose-50 p-6 text-rose-800" role="alert">
            <div className="flex items-start gap-3">
              <AlertIcon className="mt-0.5 size-5 shrink-0" />
              <div className="flex-1">
                <h2 className="font-semibold">学习数据暂时无法加载</h2>
                <p className="mt-1 text-sm">{error}</p>
              </div>
              <button type="button" onClick={() => void load()} className="rounded-xl bg-white px-3 py-2 text-xs font-semibold shadow-sm">重试</button>
            </div>
          </div>
        ) : currentDashboard?.total_topics === 0 ? (<section className="mt-7 rounded-3xl border border-slate-200 bg-white p-10 text-center"><h2 className="text-lg font-semibold text-slate-800">当前课程暂无知识点</h2><p className="mt-3 text-sm text-slate-500">课程内容准备好后会显示在这里。</p></section>) : currentDashboard && currentCurriculum ? (
          <>
            <section className="mt-7 grid gap-4 lg:grid-cols-[1.35fr_0.9fr]">
              <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-soft sm:p-6">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <span className="inline-flex items-center gap-2 text-xs font-semibold text-slate-500"><ChartIcon className="size-4 text-indigo-600" />总体进度</span>
                    <p className="mt-3 text-3xl font-bold tabular-nums text-slate-950">{currentDashboard.mastered_count}<span className="ml-1 text-base font-medium text-slate-400">/ {currentDashboard.total_topics}</span></p>
                    <p className="mt-1 text-xs text-slate-500">知识点已有掌握记录</p>
                  </div>
                  {activeStage && <span className="rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-[11px] font-semibold text-indigo-700">当前 · 阶段 {activeStage.stage}</span>}
                </div>
                <div className="mt-6"><MasteryBar value={progress} label="课程完成度" /></div>
                <div className="mt-6 grid grid-cols-3 gap-3">
                  {[
                    ["已掌握", currentDashboard.mastered_count, "text-emerald-700 bg-emerald-50"],
                    ["学习中", currentDashboard.learning_count, "text-indigo-700 bg-indigo-50"],
                    ["可开始", currentDashboard.not_started_count, "text-sky-700 bg-sky-50"],
                  ].map(([label, value, className]) => (
                    <div key={String(label)} className={`rounded-2xl p-3 ${className}`}>
                      <p className="text-xl font-bold tabular-nums">{value}</p>
                      <p className="mt-1 text-[11px] font-medium">{label}</p>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-3xl border border-indigo-200 bg-gradient-to-br from-indigo-600 to-violet-700 p-5 text-white shadow-soft sm:p-6">
                <span className="inline-flex items-center gap-2 text-xs font-semibold text-indigo-100"><TargetIcon className="size-4" />推荐下一步</span>
                <h2 className="mt-4 text-xl font-bold">{recommended?.title ?? nextActionLabel(currentDashboard.next_action)}</h2>
                <p className="mt-2 text-sm leading-6 text-indigo-100">{nextActionLabel(currentDashboard.next_action)}</p>
                {currentDashboard.reasons.length > 0 && (
                  <ul className="mt-4 space-y-1.5 text-xs leading-5 text-indigo-100">
                    {currentDashboard.reasons.slice(0, 3).map((reason) => <li key={reason} className="flex gap-2"><span aria-hidden="true">·</span><span>{reason}</span></li>)}
                  </ul>
                )}
                {recommended && (
                  <Link href={`/learn/${course}/${encodeURIComponent(recommended.id)}`} className="mt-6 inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2.5 text-sm font-semibold text-indigo-700 shadow-sm transition hover:bg-indigo-50">
                    继续学习 <ArrowRightIcon className="size-4" />
                  </Link>
                )}
              </div>
            </section>

            <section className="mt-7 grid gap-6 xl:grid-cols-[minmax(0,1fr)_310px]">
              <div className="space-y-5">
                <div className="flex items-end justify-between gap-4">
                  <div>
                    <p className="text-xs font-bold uppercase tracking-[0.16em] text-indigo-600">Curriculum</p>
                    <h2 className="mt-1 text-xl font-bold text-slate-900">课程阶段与知识点</h2>
                  </div>
                  <span className="text-xs text-slate-400">保留学习状态与历史评估</span>
                </div>
                {currentCurriculum.stages.map((stage) => (
                  <section key={stage.stage} className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
                    <div className="flex items-center justify-between gap-4">
                      <div className="flex items-center gap-3">
                        <span className="grid size-9 place-items-center rounded-xl bg-indigo-50 font-bold tabular-nums text-indigo-700">{stage.stage}</span>
                        <div>
                          <h3 className="text-sm font-bold text-slate-900">{stage.title}</h3>
                          <p className="mt-0.5 text-[11px] text-slate-400">{stage.topics.length} 个知识点</p>
                        </div>
                      </div>
                      <LayersIcon className="size-5 text-slate-300" />
                    </div>
                    <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                      {stage.topics.map((topic) => <TopicCard key={topic.id} topic={topic} course={course} />)}
                    </div>
                  </section>
                ))}
              </div>

              <aside className="space-y-5">
                <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                  <div className="flex items-center gap-2">
                    <ClockIcon className="size-4 text-indigo-600" />
                    <h2 className="text-sm font-bold text-slate-900">历史成绩</h2>
                  </div>
                  {currentDashboard.recent_practice.length === 0 ? (
                    <div className="py-8 text-center">
                      <span className="mx-auto grid size-10 place-items-center rounded-2xl bg-slate-100 text-slate-400"><ChartIcon className="size-4" /></span>
                      <p className="mt-3 text-xs leading-5 text-slate-400">暂无历史成绩。当前练习反馈在知识点对话中查看。</p>
                    </div>
                  ) : (
                    <div className="mt-4 space-y-3">
                      {currentDashboard.recent_practice.slice(0, 6).map((attempt, index) => (
                        <Link key={attempt.id ?? attempt.attempt_id ?? `${attempt.topic_id}-${index}`} href={`/learn/${course}/${encodeURIComponent(attempt.topic_id)}`} className="block rounded-2xl bg-slate-50 p-3 transition hover:bg-indigo-50">
                          <div className="flex items-start justify-between gap-3">
                            <p className="line-clamp-2 text-xs font-semibold leading-5 text-slate-700">{attempt.topic_title}</p>
                            <span className="shrink-0 text-sm font-bold tabular-nums text-indigo-700">{scoreLabel(attempt.score)}</span>
                          </div>
                          <p className="mt-1 text-[10px] text-slate-400">{attempt.mode === "checkpoint" ? "综合验收" : "主动练习"}</p>
                        </Link>
                      ))}
                    </div>
                  )}
                </section>
                <section className="rounded-3xl border border-emerald-200 bg-emerald-50 p-5">
                  <TrophyIcon className="size-5 text-emerald-700" />
                  <h2 className="mt-3 text-sm font-bold text-emerald-900">在对话中学习与练习</h2>
                  <p className="mt-2 text-xs leading-5 text-emerald-800/80">进入知识点后开始学习，可继续追问或做练习。Agent 的对话反馈不会自动转换为本地分数或掌握度。</p>
                </section>
              </aside>
            </section>
          </>
        ) : null}
      </div>
    </div>
  );
}
