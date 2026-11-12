"use client";

import { useState, useRef, useEffect, type FormEvent } from "react";
import type { ManagedTopic, TopicGroup, TopicCandidate, TopicValues } from "@/lib/topic-management";

export const fieldClass = "mt-1.5 w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900";
export const actionClass = "rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-600 hover:border-indigo-300 disabled:opacity-40";
export const primaryClass = "rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-40";
const lines = (value: FormDataEntryValue | null) => String(value ?? "").split("\n").map((s) => s.trim()).filter(Boolean);

export default function KnowledgePointEditor({ topic, reference, course, groups, catalog, placed, onSave, onCancel }: {
  topic: ManagedTopic | null; reference: boolean; course: string; groups: TopicGroup[]; catalog: TopicCandidate[];
  placed: string[]; onSave: (values: TopicValues | { topic_id: string; stage: number; stage_title: string }) => Promise<void>; onCancel: () => void;
}) {
  const chapters = groups.filter((g) => g.stage !== null);
  const initial = chapters.find((g) => g.id === topic?.parent_group_id) ?? chapters[0];
  const [chapter, setChapter] = useState(initial?.id ?? "new");
  const [selected, setSelected] = useState(topic?.prerequisite_ids ?? []);
  const [filter, setFilter] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const ref = useRef<HTMLElement>(null);
  useEffect(() => { ref.current?.scrollIntoView({ behavior: "smooth", block: "start" }); }, []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    const target = chapters.find((g) => g.id === chapter);
    const stage = target?.stage ?? Math.max(0, ...chapters.map((g) => g.stage ?? 0)) + 1;
    const stage_title = target?.title ?? String(data.get("stage_title")).trim();
    setSaving(true); setError("");
    try {
      await onSave(reference ? { topic_id: topic?.id ?? String(data.get("topic_id")), stage, stage_title } : {
        title: String(data.get("title")).trim(), description: String(data.get("description")).trim(), stage, stage_title,
        learning_objectives: lines(data.get("learning_objectives")), aliases: lines(data.get("aliases")), retrieval_keywords: lines(data.get("retrieval_keywords")),
        difficulty: String(data.get("difficulty")) as TopicValues["difficulty"], prerequisite_ids: selected,
      });
    } catch (cause) { setError(cause instanceof Error ? cause.message : "保存失败"); }
    finally { setSaving(false); }
  }
  const candidates = catalog.filter((t) => t.id !== topic?.id && `${t.title} ${t.course_title} ${t.id}`.toLowerCase().includes(filter.toLowerCase()));
  return <section ref={ref} className="mt-6 scroll-mt-4 rounded-2xl border border-indigo-200 bg-white p-5 sm:p-6" aria-label="知识点编辑器">
    <h2 className="text-lg font-bold text-slate-900">{reference ? topic ? "调整引用位置" : "引用其他课程知识点" : topic ? "编辑知识点" : "新增知识点"}</h2>
    <form onSubmit={submit} className="mt-5"><fieldset disabled={saving} className="grid gap-4 sm:grid-cols-2">
      {reference ? <label className="text-sm text-slate-700 sm:col-span-2">引用知识点{topic ? <p className="mt-2 font-semibold">{topic.title} · {topic.owner_title}</p> : <select name="topic_id" required className={fieldClass} defaultValue=""><option value="" disabled>选择其他课程的知识点</option>{catalog.filter((t) => t.course !== course && !placed.includes(t.id)).map((t) => <option key={t.id} value={t.id}>{t.course_title} / {t.title}</option>)}</select>}<span className="mt-2 block text-xs text-slate-500">内容由所属课程维护，此处调整本课程目录中的位置。</span></label> : <label className="text-sm text-slate-700 sm:col-span-2">知识点名称<input autoFocus name="title" required maxLength={100} defaultValue={topic?.title} className={fieldClass} /></label>}
      <label className="text-sm text-slate-700">所在章节<select aria-label="所在章节" value={chapter} onChange={(e) => setChapter(e.target.value)} className={fieldClass}>{chapters.map((g) => <option key={g.id} value={g.id}>{g.title}</option>)}<option value="new">新建章节</option></select></label>
      {chapter === "new" && <label className="text-sm text-slate-700">新章节名称<input name="stage_title" required maxLength={100} className={fieldClass} /></label>}
      {!reference && <>
        <label className="text-sm text-slate-700 sm:col-span-2">知识点简介<textarea name="description" rows={3} maxLength={2000} defaultValue={topic?.description} className={fieldClass} /></label>
        <label className="text-sm text-slate-700 sm:col-span-2">学习目标（每行一项）<textarea name="learning_objectives" rows={3} defaultValue={topic?.learning_objectives.join("\n")} className={fieldClass} /></label>
        <div className="sm:col-span-2"><p className="text-sm font-medium text-slate-700">必需前置知识点</p><input aria-label="筛选前置知识点" placeholder="按名称或课程筛选" value={filter} onChange={(e) => setFilter(e.target.value)} className={fieldClass} /><div className="mt-2 max-h-48 overflow-y-auto rounded-xl border border-slate-200 p-3">{candidates.map((t) => <label key={t.id} className="flex items-start gap-2 py-1.5 text-sm text-slate-600"><input type="checkbox" className="mt-1 accent-indigo-600" checked={selected.includes(t.id)} onChange={(e) => setSelected(e.target.checked ? [...selected, t.id] : selected.filter((id) => id !== t.id))} />{t.title}<span className="text-xs text-slate-400">{t.course_title}</span></label>)}{selected.filter((id) => !catalog.some((t) => t.id === id)).map((id) => <label key={id} className="flex gap-2 py-1 text-sm text-amber-700"><input type="checkbox" checked onChange={() => setSelected(selected.filter((key) => key !== id))} />{id}（已不可用，取消选择后保存）</label>)}{!candidates.length && <p className="text-sm text-slate-400">没有匹配的知识点</p>}</div></div>
        <details className="sm:col-span-2"><summary className="cursor-pointer text-sm font-medium text-slate-600">更多设置</summary><div className="mt-3 grid gap-4 sm:grid-cols-2"><label className="text-sm text-slate-700">别名（每行一项）<textarea name="aliases" rows={3} defaultValue={topic?.aliases.join("\n")} className={fieldClass} /></label><label className="text-sm text-slate-700">检索关键词（每行一项）<textarea name="retrieval_keywords" rows={3} defaultValue={topic?.retrieval_keywords.join("\n")} className={fieldClass} /></label><label className="text-sm text-slate-700">难度<select name="difficulty" defaultValue={topic?.difficulty ?? "medium"} className={fieldClass}><option value="easy">基础</option><option value="medium">进阶</option><option value="hard">较难</option></select></label></div></details>
      </>}
    </fieldset>{error && <p role="alert" className="mt-4 rounded-xl bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}<div className="mt-5 flex justify-end gap-3"><button type="button" disabled={saving} onClick={onCancel} className={actionClass}>取消</button><button type="submit" disabled={saving} className={primaryClass}>{saving ? "正在保存…" : "保存编排"}</button></div></form>
  </section>;
}
