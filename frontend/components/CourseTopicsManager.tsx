"use client";

import { useEffect, useRef, useState } from "react";
import { useAdmin } from "@/components/AdminProvider";
import KnowledgePointEditor, { actionClass, fieldClass, primaryClass } from "@/components/KnowledgePointEditor";
import { manageTopics, topicCatalog, type ManagedOutline, type ManagedTopic, type TopicCandidate, type TopicGroup, type TopicValues } from "@/lib/topic-management";

const message = (error: unknown) => error instanceof Error ? error.message : "操作失败，请重试。";
export default function CourseTopicsManager({ courseId, onInteractionChange }: { courseId: string; onInteractionChange?: (busy: boolean) => void }) {
  const { withAdmin } = useAdmin();
  const [outline, setOutline] = useState<ManagedOutline | null>(null);
  const [catalog, setCatalog] = useState<TopicCandidate[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [version, setVersion] = useState(0);
  const [busy, setBusy] = useState(false);
  const [editor, setEditor] = useState<{ topic: ManagedTopic | null; reference: boolean } | null>(null);
  const [removing, setRemoving] = useState<ManagedTopic | null>(null);
  const [renaming, setRenaming] = useState<TopicGroup | null>(null);
  const renamePanel = useRef<HTMLFormElement>(null);
  const removePanel = useRef<HTMLElement>(null);
  useEffect(() => {
    if (renaming) {
      renamePanel.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      renamePanel.current?.querySelector("input")?.focus({ preventScroll: true });
    }
  }, [renaming]);
  useEffect(() => {
    if (removing) {
      removePanel.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      removePanel.current?.focus({ preventScroll: true });
    }
  }, [removing]);
  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setError("");
      try {
        const [data, candidates] = await withAdmin((token) => Promise.all([manageTopics(token, courseId, "GET", "", undefined, controller.signal), topicCatalog(token, controller.signal)]));
        if (!controller.signal.aborted) { setOutline(data); setCatalog(candidates); }
      } catch (cause) { if (!controller.signal.aborted) setError(message(cause)); }
    }, 0);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [courseId, version, withAdmin]);
  async function mutate(method: string, suffix: string, body?: unknown) {
    setBusy(true); setError(""); setNotice("");
    try {
      const data = await withAdmin((token) => manageTopics(token, courseId, method, suffix, body));
      setOutline(data); setNotice("编排已保存，学生端目录已同步。");
      setCatalog((previous) => [...previous.filter((t) => t.course !== courseId), ...data.groups.flatMap((g) => g.topics).filter((t) => !t.is_reference && t.active).map((t) => ({ id: t.id, title: t.title, course: courseId, course_title: data.course.title }))]);
    } finally { setBusy(false); }
  }
  async function act(action: () => Promise<void>) { try { await action(); } catch (cause) { setError(message(cause)); } }
  async function save(values: TopicValues | { topic_id: string; stage: number; stage_title: string }) {
    if (!editor) return;
    const suffix = editor.reference ? editor.topic ? `/references/${editor.topic.id}` : "/references" : editor.topic ? `/${editor.topic.id}` : "";
    await mutate(editor.topic ? "PUT" : "POST", suffix, values); setEditor(null);
  }
  function moveTopic(group: TopicGroup, index: number, offset: number) {
    const ids = group.topics.map((t) => t.id); [ids[index], ids[index + offset]] = [ids[index + offset], ids[index]];
    void act(() => mutate("PUT", "/order", { group_id: group.id, topic_ids: ids }));
  }
  function moveGroup(group: TopicGroup, offset: number) {
    const ids = outline!.groups.filter((g) => g.stage !== null).map((g) => g.id); const index = ids.indexOf(group.id);
    [ids[index], ids[index + offset]] = [ids[index + offset], ids[index]];
    void act(() => mutate("POST", "/groups/order", { group_ids: ids }));
  }
  const interactionBusy = busy || Boolean(editor) || Boolean(removing) || Boolean(renaming);
  useEffect(() => { onInteractionChange?.(interactionBusy); }, [interactionBusy, onInteractionChange]);
  const chapters = outline?.groups.filter((g) => g.stage !== null) ?? [];
  return <section aria-label="知识点编排" className="mt-8">
    <div className="mt-4 flex flex-wrap items-start justify-between gap-4"><div><h2 className="text-xl font-bold text-slate-900">知识点编排</h2><p className="mt-2 text-sm text-slate-500">管理章节和学习顺序，讲解内容由 Dify Agent 提供。</p></div><div className="flex flex-wrap gap-2"><button disabled={!outline || interactionBusy} className={actionClass} onClick={() => setEditor({ topic: null, reference: true })}>引用知识点</button><button disabled={!outline || interactionBusy} className={primaryClass} onClick={() => setEditor({ topic: null, reference: false })}>新增知识点</button></div></div>
    {error && <div role="alert" className="mt-5 flex justify-between gap-4 rounded-xl bg-rose-50 p-3 text-sm text-rose-700"><p>{error}</p><button disabled={busy} onClick={() => { setOutline(null); setVersion((v) => v + 1); }} className="shrink-0 underline">刷新目录</button></div>}
    {notice && <p role="status" className="mt-4 text-sm text-emerald-700">{notice}</p>}
    {editor && outline && <KnowledgePointEditor key={editor.topic?.id ?? String(editor.reference)} {...editor} course={courseId} groups={outline.groups} catalog={catalog} placed={outline.groups.flatMap((g) => g.topics.map((t) => t.id))} onSave={save} onCancel={() => setEditor(null)} />}
    {renaming && <form ref={renamePanel} aria-label="重命名章节" className="mt-5 flex flex-wrap items-end gap-3 rounded-xl border border-indigo-200 bg-white p-4" onSubmit={(e) => { e.preventDefault(); const title = String(new FormData(e.currentTarget).get("chapter_title")).trim(); void act(async () => { await mutate("PATCH", `/groups/${renaming.stage}`, { title }); setRenaming(null); }); }}><label className="flex-1 text-sm text-slate-600">章节名称<input name="chapter_title" required maxLength={100} defaultValue={renaming.title} className={fieldClass} /></label><button disabled={busy} className={primaryClass}>保存名称</button><button disabled={busy} type="button" className={actionClass} onClick={() => setRenaming(null)}>取消</button></form>}
    {removing && <section ref={removePanel} tabIndex={-1} aria-label="确认移除知识点" className="mt-5 rounded-xl border border-rose-200 bg-white p-4"><p className="text-sm text-slate-700">确定{removing.is_reference ? "移除此课程中的引用" : "移除知识点"}“{removing.title}”？已有学习记录会保留。</p><div className="mt-3 flex gap-3"><button disabled={busy} className="rounded-xl bg-rose-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40" onClick={() => void act(async () => { await mutate("DELETE", `${removing.is_reference ? "/references" : ""}/${removing.id}`); setRemoving(null); })}>确认移除</button><button disabled={busy} className={actionClass} onClick={() => setRemoving(null)}>取消</button></div></section>}
    {!outline && !error && <p role="status" className="py-10 text-slate-500">正在加载知识点…</p>}
    {outline && !outline.groups.length && <div className="mt-8 rounded-2xl border border-dashed border-slate-300 p-10 text-center text-sm text-slate-500">暂无知识点，新增知识点时即可创建第一个章节。</div>}
    <div className="mt-6 space-y-5">{outline?.groups.map((group) => <section key={group.id} className="overflow-hidden rounded-2xl border border-slate-200 bg-white" aria-label={group.title}>
      <div className="flex flex-wrap items-center justify-between gap-3 bg-slate-50 px-5 py-4"><h2 className="font-semibold text-slate-800">{group.title}<span className="ml-3 text-xs font-normal text-slate-400">{group.topics.length} 个知识点</span></h2>{group.stage !== null && <div className="flex gap-2"><button disabled={interactionBusy || group.id === chapters[0]?.id} aria-label={`上移章节${group.title}`} className={actionClass} onClick={() => moveGroup(group, -1)}>↑</button><button disabled={interactionBusy || group.id === chapters.at(-1)?.id} aria-label={`下移章节${group.title}`} className={actionClass} onClick={() => moveGroup(group, 1)}>↓</button><button disabled={interactionBusy} className={actionClass} onClick={() => setRenaming(group)}>重命名章节</button></div>}</div>
      <ol className="divide-y divide-slate-100">{group.topics.map((topic, index) => <li key={topic.id} className="flex flex-wrap items-center gap-3 px-5 py-4"><span className="w-5 text-sm tabular-nums text-slate-400">{index + 1}</span><div className="min-w-0 flex-1"><p className="break-words font-medium text-slate-800">{topic.title}{topic.is_reference && <span className="ml-2 rounded bg-indigo-50 px-2 py-0.5 text-xs text-indigo-600">引用 · {topic.owner_title}</span>}</p>{topic.description && <p className="mt-1 line-clamp-2 text-sm text-slate-500">{topic.description}</p>}{!topic.available && <p className="mt-1 text-xs text-amber-700">此知识点或所属课程当前不可用</p>}</div><div className="flex w-full flex-wrap items-center justify-end gap-2 pl-8 sm:w-auto sm:pl-0"><button disabled={interactionBusy || index === 0} aria-label={`上移${topic.title}`} className={actionClass} onClick={() => moveTopic(group, index, -1)}>↑</button><button disabled={interactionBusy || index === group.topics.length - 1} aria-label={`下移${topic.title}`} className={actionClass} onClick={() => moveTopic(group, index, 1)}>↓</button><button disabled={interactionBusy} aria-label={`编辑${topic.title}`} className={actionClass} onClick={() => setEditor({ topic, reference: topic.is_reference })}>{topic.is_reference ? "调整位置" : "编辑"}</button><button disabled={interactionBusy} aria-label={`移除${topic.title}`} className={`${actionClass} text-rose-700`} onClick={() => setRemoving(topic)}>移除</button></div></li>)}</ol>{!group.topics.length && <p className="px-5 py-6 text-sm text-slate-400">暂无展示中的知识点</p>}
    </section>)}</div>
    {!!outline?.removed_topics.length && <details className="mt-8 rounded-2xl border border-slate-200 bg-white p-5"><summary className="cursor-pointer text-sm font-medium text-slate-600">已移除的知识点（{outline.removed_topics.length}）</summary><ul className="mt-3 divide-y divide-slate-100">{outline.removed_topics.map((t) => <li key={t.id} className="flex items-center justify-between gap-4 py-3 text-sm"><span>{t.title}<span className="ml-2 text-slate-400">{t.stage_title}</span></span><button disabled={interactionBusy} className={actionClass} onClick={() => void act(() => mutate("POST", `/${t.id}/restore`))}>恢复知识点</button></li>)}</ul></details>}
  </section>;
}
