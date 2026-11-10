"use client";
import Link from "next/link";
import { useState } from "react";
import { useStudent } from "./StudentProvider";
import { useCourseOutline } from "./CourseLayout";
import { createPrerequisiteTest } from "@/lib/api-content";
import type { Assessment, PrerequisiteEdge, Prerequisites } from "@/lib/types-content";
import { COURSE_META } from "@/lib/types";

export default function TopicPrerequisiteCard({ data, onAssessment }: { data: Prerequisites; onAssessment: (assessment: Assessment) => void }) {
  const { topicHref, outline } = useCourseOutline();
  const { withStudent } = useStudent();
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  async function test(prerequisiteId?: string) {
    setBusy(prerequisiteId || "all"); setError("");
    try { onAssessment(await withStudent((id) => createPrerequisiteTest(data.topic_id, id, prerequisiteId))); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "前置小测暂不可用。"); }
    finally { setBusy(""); }
  }
  function edgeCard(edge: PrerequisiteEdge) {
    const namedCompetencies = edge.required_competencies.filter((competency) => !/^[a-z0-9_.-]+$/i.test(competency));
    const canonicalObjectives = outline?.groups.flatMap((group) => group.topics).find((topic) => topic.topic_id === edge.prerequisite_topic_id)?.learning_objectives ?? [];
    const goals = namedCompetencies.length ? namedCompetencies : canonicalObjectives.slice(0, 2);
    return <li key={`${edge.id}:${edge.scope}:${edge.section_id || ""}`} className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap justify-between gap-2"><Link href={topicHref({ topic_id: edge.prerequisite_topic_id, owner_course: edge.course })} className="text-sm font-bold text-indigo-700">{edge.title} ↗</Link><span className="text-xs text-slate-500">{edge.satisfied ? "✓ 已满足" : edge.scope === "lesson_section" ? "分节学习提示" : "○ 建议补充"}</span></div>
      <p className="mt-1 text-[11px] text-slate-400">{COURSE_META[edge.course].label}{edge.scope === "lesson_section" ? ` · 用于 ${edge.section_id || "相关推导分节"}` : ""}</p>
      <p className="mt-2 text-xs leading-6 text-slate-600">{edge.reason}</p>
      {goals.length > 0 && <p className="mt-2 text-xs leading-5 text-slate-500">需要能做到：{goals.join("；")}</p>}
      {edge.relation_type === "required" && !edge.satisfied && edge.scope === "topic" && <button type="button" disabled={Boolean(busy)} onClick={() => void test(edge.prerequisite_topic_id)} className="mt-3 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-xs font-semibold text-indigo-700 disabled:opacity-50">{busy === edge.prerequisite_topic_id ? "AI 正在按资料出题…" : "做前置小测"}</button>}
    </li>;
  }
  return <section id="prerequisites" className="rounded-3xl border border-slate-200 bg-white p-5 sm:p-7">
    <h2 className="text-lg font-bold text-slate-900">学它之前需要什么</h2>
    {data.unmet.length > 0 ? <div className="mt-4 rounded-2xl bg-amber-50 p-4 text-sm text-amber-900"><p className="font-semibold">你可能需要先补充：{data.unmet.map((item) => item.title).join("、")}。</p><p className="mt-2 text-xs leading-6">可以继续阅读讲解、例题和辅助练习。前置小测由 AI 根据对应课程资料动态出题；通过只证明本次涉及的技能，正式测试仍需满足对应前置能力。</p><div className="mt-3 flex flex-wrap gap-4"><button type="button" disabled={Boolean(busy)} onClick={() => void test()} className="font-semibold text-indigo-700">{busy === "all" ? "AI 正在按资料出题…" : "做前置小测（3–5 题）"}</button><a href="#lesson" className="font-semibold text-indigo-700">继续预览 ↓</a></div></div> : <p className="mt-3 text-sm text-emerald-700">✓ 当前必需前置已满足，可以继续学习。</p>}
    {error && <div role="alert" className="mt-4 rounded-xl bg-rose-50 p-3 text-xs leading-6 text-rose-800">{error} 可以先点击知识点补学；若对应课程资料不足，请在 Dify 中补充资料并检查引用配置后重试。</div>}
    {data.required.length > 0 && <><h3 className="mt-5 text-xs font-bold text-slate-500">必需知识 · 推导分节要求单独标注</h3><ul className="mt-3 grid gap-3 xl:grid-cols-2">{data.required.map(edgeCard)}</ul></>}
    {data.recommended.length > 0 && <details className="mt-5"><summary className="cursor-pointer text-sm font-semibold text-slate-700">建议提前了解（不影响开始学习）</summary><ul className="mt-3 grid gap-3 xl:grid-cols-2">{data.recommended.map(edgeCard)}</ul></details>}
    {data.related.length > 0 && <details className="mt-5"><summary className="cursor-pointer text-sm font-semibold text-slate-700">相关拓展</summary><ul className="mt-3 grid gap-3 xl:grid-cols-2">{data.related.map(edgeCard)}</ul></details>}
  </section>;
}
