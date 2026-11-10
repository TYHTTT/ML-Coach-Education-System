"use client";

import { useState } from "react";
import MarkdownRenderer from "./MarkdownRenderer";
import SourcePanel from "./SourcePanel";
import { useStudent } from "./StudentProvider";
import { askExample, exposeExample } from "@/lib/api-content";
import type { ExampleStep, Lesson, WorkedExampleData } from "@/lib/types-content";
import type { Source } from "@/lib/types";

export function ContentOrigin({ origin, version }: { origin: string; version: number }) {
  return <p className="text-xs text-slate-500">{origin === "instructor_authored" ? "项目自编教学示例" : origin === "source_derived" ? "根据课程资料整理" : "生成草稿，待审核"} · 内容版本 {version}</p>;
}

export default function LessonContent({ lesson }: { lesson: Lesson }) {
  return <section id="lesson" className="lesson-panel scroll-mt-24 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7">
    <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-xl font-bold text-slate-900">知识讲解</h2><ContentOrigin origin={lesson.content_origin} version={lesson.version} /></div>
    <div className="mt-5 rounded-2xl bg-indigo-50 p-5"><h3 className="mb-2 text-sm font-bold text-indigo-900">从这个问题开始</h3><MarkdownRenderer content={lesson.motivating_problem} /></div>
    <div className="mt-6 space-y-5">{lesson.key_concepts.map((concept, index) => <div key={index}><MarkdownRenderer content={concept} /></div>)}</div>
    {lesson.formulas.map((formula, index) => <div key={index} className="mt-5 min-w-0 rounded-2xl border border-slate-200 bg-slate-50 p-4"><MarkdownRenderer content={formula.expression.includes("$") ? formula.expression : `$$\n${formula.expression}\n$$`} /><p className="mt-2 text-sm font-semibold text-slate-700">符号与形状</p><MarkdownRenderer content={formula.symbols} /><p className="mt-3 text-xs text-slate-500">适用条件：{formula.conditions}</p></div>)}
    <div className="mt-6 border-t border-slate-100 pt-5"><h3 className="text-sm font-bold text-slate-900">小结</h3><MarkdownRenderer content={lesson.summary} /></div>
    {lesson.practice_recommendations.length > 0 && <div className="mt-4 rounded-xl bg-emerald-50 p-4"><h3 className="text-sm font-bold text-emerald-900">接下来自己做</h3><ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-emerald-900">{lesson.practice_recommendations.map((item, index) => <li key={item}>{/^bank[.:_-]/i.test(item) ? <a href="#practice" className="underline decoration-emerald-300 underline-offset-4">练习 {index + 1}：检验本节学习目标</a> : item}</li>)}</ul><a href="#practice" className="mt-3 inline-block text-sm font-semibold text-indigo-700">进入独立练习 →</a></div>}
    {lesson.source_refs.length > 0 && <details className="mt-5"><summary className="cursor-pointer text-sm font-semibold text-indigo-700">课程讲解来源</summary><div className="mt-3"><SourcePanel sources={lesson.source_refs} /></div></details>}
  </section>;
}

function ExampleStepCard({ step, example, askDisabled }: { step: ExampleStep; example: WorkedExampleData; askDisabled: boolean }) {
  const { withStudent } = useStudent();
  const [question, setQuestion] = useState("");
  const [response, setResponse] = useState<{ answer: string; sources: Source[] } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function ask() {
    if (!question.trim() || busy || askDisabled) return;
    setBusy(true); setError("");
    try { setResponse(await withStudent((id) => askExample(example, step.step_id, question.trim(), id))); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "步骤答疑暂不可用，请重试。"); }
    finally { setBusy(false); }
  }
  return <li className="min-w-0 rounded-2xl border border-slate-200 bg-white p-4 sm:p-5">
    <h4 className="text-sm font-bold text-indigo-900">{step.title}</h4><MarkdownRenderer content={step.explanation} />
    {step.formula && <MarkdownRenderer content={step.formula.includes("$") ? step.formula : `$$\n${step.formula}\n$$`} />}
    {step.substitution && <div className="mt-3 rounded-xl bg-slate-50 p-3"><p className="text-xs font-bold text-slate-600">代入与计算</p><MarkdownRenderer content={step.substitution} /></div>}
    {step.result && <div className="mt-3"><p className="text-xs font-bold text-emerald-800">这一步的结果</p><MarkdownRenderer content={step.result} /></div>}
    {step.justification && <p className="mt-3 text-xs leading-6 text-slate-500">依据：{step.justification}</p>}
    <details className="mt-4 border-t border-slate-100 pt-3"><summary className="cursor-pointer text-xs font-semibold text-indigo-700">针对这一步提问</summary>
      {askDisabled ? <p className="mt-3 text-xs text-slate-500">正式测试进行中，提交后可继续步骤答疑。</p> : <form onSubmit={(event) => { event.preventDefault(); void ask(); }} className="mt-3"><label htmlFor={`ask-${example.id}-${step.step_id}`} className="text-xs text-slate-600">你的疑问</label><textarea id={`ask-${example.id}-${step.step_id}`} value={question} onChange={(event) => setQuestion(event.target.value)} rows={2} className="mt-2 w-full rounded-xl border border-slate-200 p-3 text-sm" placeholder="例如：为什么这里对偏置求导是 1？" /><button type="submit" disabled={busy || !question.trim()} className="mt-2 rounded-lg bg-indigo-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">{busy ? "正在回答…" : "询问这个步骤"}</button></form>}
      {error && <p role="alert" className="mt-3 text-xs text-rose-700">{error} 可以稍后重试，已保存的例题仍可阅读。</p>}
      {response && <div className="mt-4 border-t border-slate-100 pt-3"><MarkdownRenderer content={response.answer} />{response.sources.length > 0 && <details className="mt-3"><summary className="text-xs text-indigo-700">答疑来源</summary><SourcePanel sources={response.sources} /></details>}</div>}
    </details>
  </li>;
}

export function WorkedExample({ example, askDisabled = false }: { example: WorkedExampleData; askDisabled?: boolean }) {
  const { withStudent } = useStudent();
  const [exposed, setExposed] = useState(false);
  const [error, setError] = useState("");
  async function recordExposure() {
    if (exposed) return;
    setExposed(true);
    try { await withStudent((id) => exposeExample(example, id)); }
    catch { setError("暂未记录例题阅读，请检查连接后重新展开。阅读本身不会增加掌握度。"); setExposed(false); }
  }
  return <article className="lesson-panel rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7">
    <h3 className="text-lg font-bold text-slate-900">{example.title}</h3><div className="mt-2"><ContentOrigin origin={example.content_origin} version={example.version} /></div>
    <div className="mt-4"><MarkdownRenderer content={example.problem} /></div>
    <dl className="mt-4 grid gap-2 rounded-xl bg-slate-50 p-4 sm:grid-cols-2">{Object.entries(example.givens).map(([key, value]) => <div key={key} className="min-w-0 text-sm"><dt className="font-semibold text-slate-500">{key}</dt><dd className="mt-1 break-words text-slate-800">{typeof value === "string" ? value : JSON.stringify(value)}</dd></div>)}</dl>
    <p className="mt-4 text-sm text-slate-700"><span className="font-semibold">目标：</span>{example.target}</p>
    <details className="mt-5" onToggle={(event) => { if (event.currentTarget.open) void recordExposure(); }}>
      <summary className="cursor-pointer rounded-xl bg-indigo-50 px-4 py-3 text-sm font-bold text-indigo-800">展开完整分步解法</summary>
      {error && <p className="mt-3 text-xs text-amber-800" role="alert">{error}</p>}
      <div className="my-4"><MarkdownRenderer content={example.solution_outline} /></div>
      <ol className="space-y-4">{example.steps.map((step) => <ExampleStepCard key={step.step_id} step={step} example={example} askDisabled={askDisabled} />)}</ol>
      <div className="mt-5 rounded-2xl bg-emerald-50 p-4"><h4 className="text-sm font-bold text-emerald-900">最终结果</h4><MarkdownRenderer content={example.final_answer} /></div>
      {example.common_mistakes.length > 0 && <div className="mt-5"><h4 className="text-sm font-bold text-amber-900">常见错误</h4><ul className="mt-2 list-disc space-y-2 pl-5 text-sm text-slate-600">{example.common_mistakes.map((item) => <li key={item}>{item}</li>)}</ul></div>}
      <p className="mt-5 text-xs text-slate-400">这是教学例题，阅读不会自动计为掌握。练习与测试由 AI 按课程资料生成，提交后会提供评价。</p>
    </details>
    {example.source_refs.length > 0 && <details className="mt-5"><summary className="text-xs font-semibold text-indigo-700">例题来源</summary><div className="mt-3"><SourcePanel sources={example.source_refs} /></div></details>}
  </article>;
}
