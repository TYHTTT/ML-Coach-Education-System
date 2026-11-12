"use client";

import { useState, useRef, useEffect, useId, type FormEvent } from "react";
import type { ManagedTopic, TopicGroup, TopicCandidate, TopicValues } from "@/lib/topic-management";

export const fieldClass = "mt-1.5 w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900";
export const actionClass = "rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-600 hover:border-indigo-300 disabled:opacity-40";
export const primaryClass = "rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-40";
const lines = (value: FormDataEntryValue | null) => String(value ?? "").split("\n").map((s) => s.trim()).filter(Boolean);

export default function KnowledgePointEditor({ topic, reference, course, groups, catalog, placed, returnFocus, onSave, onCancel }: {
  topic: ManagedTopic | null; reference: boolean; course: string; groups: TopicGroup[]; catalog: TopicCandidate[];
  placed: string[]; returnFocus: HTMLElement; onSave: (values: TopicValues | { topic_id: string; stage: number; stage_title: string }) => Promise<void>; onCancel: () => void;
}) {
  const chapters = groups.filter((g) => g.stage !== null);
  const initial = chapters.find((g) => g.id === topic?.parent_group_id) ?? chapters[0];
  const [chapter, setChapter] = useState(initial?.id ?? "new");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const ref = useRef<HTMLDialogElement>(null);
  const headingId = useId();
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    const trigger = returnFocus;
    const position = { left: window.scrollX, top: window.scrollY };
    const { overflow, paddingRight } = document.body.style;
    const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;
    if (scrollbarWidth > 0) {
      document.body.style.paddingRight = `${parseFloat(getComputedStyle(document.body).paddingRight) + scrollbarWidth}px`;
    }
    document.body.style.overflow = "hidden";
    dialog.showModal();
    dialog.querySelector<HTMLElement>('input[name="title"], select')?.focus({ preventScroll: true });
    return () => {
      dialog.close();
      document.body.style.overflow = overflow;
      document.body.style.paddingRight = paddingRight;
      window.scrollTo({ ...position, behavior: "instant" });
      requestAnimationFrame(() => {
        if (trigger?.isConnected) trigger.focus({ preventScroll: true });
      });
    };
  }, [returnFocus]);
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
        difficulty: String(data.get("difficulty")) as TopicValues["difficulty"],
      });
    } catch (cause) { setError(cause instanceof Error ? cause.message : "保存失败"); }
    finally { setSaving(false); }
  }
  return <dialog ref={ref} aria-labelledby={headingId} onCancel={(event) => { event.preventDefault(); if (!saving) onCancel(); }} onKeyDown={(event) => {
    if (event.key !== "Tab" || event.ctrlKey || event.metaKey || event.altKey) return;
    const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>("button, input, textarea, select, summary, [tabindex]"))
      .filter((element) => element.tabIndex >= 0 && !element.matches(":disabled") && element.getClientRects().length > 0);
    const first = controls[0], last = controls.at(-1);
    if (!first) { event.preventDefault(); event.currentTarget.focus(); }
    else if (event.shiftKey && (document.activeElement === first || document.activeElement === event.currentTarget)) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }} className="m-auto max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] max-w-2xl overflow-hidden rounded-2xl border border-slate-200 bg-white p-0 shadow-xl backdrop:bg-slate-950/40">
    <form onSubmit={submit} className="flex max-h-[calc(100dvh-2rem)] flex-col">
      <header className="flex shrink-0 items-center justify-between gap-4 border-b border-slate-100 px-5 py-4 sm:px-6">
        <h2 id={headingId} className="text-lg font-bold text-slate-900">{reference ? topic ? "调整引用位置" : "引用其他课程知识点" : topic ? "编辑知识点" : "新增知识点"}</h2>
        <button type="button" aria-label="关闭知识点编辑器" disabled={saving} onClick={onCancel} className="flex size-9 shrink-0 items-center justify-center rounded-lg text-xl text-slate-500 hover:bg-slate-100 disabled:opacity-40">×</button>
      </header>
      <div className="min-h-0 overflow-y-auto overscroll-contain p-5 sm:p-6"><fieldset disabled={saving} className="grid gap-4 sm:grid-cols-2">
      {reference ? <label className="text-sm text-slate-700 sm:col-span-2">引用知识点{topic ? <p className="mt-2 font-semibold">{topic.title} · {topic.owner_title}</p> : <select name="topic_id" required className={fieldClass} defaultValue=""><option value="" disabled>选择其他课程的知识点</option>{catalog.filter((t) => t.course !== course && !placed.includes(t.id)).map((t) => <option key={t.id} value={t.id}>{t.course_title} / {t.title}</option>)}</select>}<span className="mt-2 block text-xs text-slate-500">内容由所属课程维护，此处调整本课程目录中的位置。</span></label> : <label className="text-sm text-slate-700 sm:col-span-2">知识点名称<input name="title" required maxLength={100} defaultValue={topic?.title} className={fieldClass} /></label>}
      <label className="text-sm text-slate-700">所在章节<select aria-label="所在章节" value={chapter} onChange={(e) => setChapter(e.target.value)} className={fieldClass}>{chapters.map((g) => <option key={g.id} value={g.id}>{g.title}</option>)}<option value="new">新建章节</option></select></label>
      {chapter === "new" && <label className="text-sm text-slate-700">新章节名称<input name="stage_title" required maxLength={100} className={fieldClass} /></label>}
      {!reference && <>
        <label className="text-sm text-slate-700 sm:col-span-2">知识点简介<textarea name="description" rows={3} maxLength={2000} defaultValue={topic?.description} className={fieldClass} /></label>
        <label className="text-sm text-slate-700 sm:col-span-2">学习目标（每行一项）<textarea name="learning_objectives" rows={3} defaultValue={topic?.learning_objectives.join("\n")} className={fieldClass} /></label>
        <details className="sm:col-span-2"><summary className="cursor-pointer text-sm font-medium text-slate-600">更多设置</summary><div className="mt-3 grid gap-4 sm:grid-cols-2"><label className="text-sm text-slate-700">别名（每行一项）<textarea name="aliases" rows={3} defaultValue={topic?.aliases.join("\n")} className={fieldClass} /></label><label className="text-sm text-slate-700">检索关键词（每行一项）<textarea name="retrieval_keywords" rows={3} defaultValue={topic?.retrieval_keywords.join("\n")} className={fieldClass} /></label><label className="text-sm text-slate-700">难度<select name="difficulty" defaultValue={topic?.difficulty ?? "medium"} className={fieldClass}><option value="easy">基础</option><option value="medium">进阶</option><option value="hard">较难</option></select></label></div></details>
      </>}
      </fieldset></div>
      <footer className="shrink-0 border-t border-slate-100 px-5 py-4 sm:px-6">
        {error && <p role="alert" className="mb-3 rounded-xl bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}
        <div className="flex justify-end gap-3"><button type="button" disabled={saving} onClick={onCancel} className={actionClass}>取消</button><button type="submit" disabled={saving} className={primaryClass}>{saving ? "正在保存…" : "保存编排"}</button></div>
      </footer>
    </form>
  </dialog>;
}
