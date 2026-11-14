"use client";

import { useEffect, useId, useRef, useState } from "react";
import type { ManagedTopic, TopicGroup } from "@/lib/topic-management";
import { actionClass } from "@/components/KnowledgePointEditor";

export default function DeleteChapterDialog({ group, topics, returnFocus, onDelete, onCancel, onReload }: {
  group: TopicGroup; topics: ManagedTopic[]; returnFocus: HTMLElement;
  onDelete: () => Promise<void>; onCancel: () => void; onReload: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const messageId = useId();
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");
  const legacyCount = topics.filter(topic => !topic.active).length;
  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    const trigger = returnFocus;
    const position = { left: window.scrollX, top: window.scrollY };
    const { overflow, paddingRight } = document.body.style;
    const scrollbar = window.innerWidth - document.documentElement.clientWidth;
    if (scrollbar > 0) document.body.style.paddingRight = `${parseFloat(getComputedStyle(document.body).paddingRight) + scrollbar}px`;
    document.body.style.overflow = "hidden";
    element.showModal(); cancel.current?.focus({ preventScroll: true });
    return () => {
      element.close();
      document.body.style.overflow = overflow; document.body.style.paddingRight = paddingRight;
      window.scrollTo({ ...position, behavior: "instant" });
      requestAnimationFrame(() => { if (trigger.isConnected) trigger.focus({ preventScroll: true }); });
    };
  }, [returnFocus]);
  async function remove() {
    setDeleting(true); setError("");
    try { await onDelete(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "删除失败，请重试。"); }
    finally { setDeleting(false); }
  }
  return <dialog ref={dialog} aria-labelledby={titleId} aria-describedby={messageId} aria-label="删除章节确认" onCancel={event => { event.preventDefault(); if (!deleting) onCancel(); }} className="m-auto max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] max-w-lg overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl backdrop:bg-slate-950/40 open:flex open:flex-col">
    <header className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
      <h2 id={titleId} className="text-lg font-bold text-slate-900">删除章节</h2>
      <button type="button" disabled={deleting} onClick={onCancel} aria-label="关闭章节删除确认" className="size-8 rounded-lg text-xl text-slate-500 hover:bg-slate-100 disabled:opacity-40">×</button>
    </header>
    <div className="min-h-0 overflow-y-auto overscroll-contain p-5">
      <p id={messageId} className="break-words text-sm leading-6 text-slate-700">确定永久删除“{group.title}”章节及其中的 <strong>{topics.length}</strong> 个知识点？</p>
      {legacyCount > 0 && <p className="mt-2 text-xs text-slate-500">包含 {legacyCount} 个历史待清理知识点。</p>}
      <ul aria-label="将被删除的知识点" className="mt-4 max-h-48 list-disc space-y-1 overflow-y-auto rounded-xl bg-slate-50 py-3 pl-8 pr-4 text-sm text-slate-600">{topics.map(topic => <li key={topic.id} className="break-words">{topic.title}{!topic.active && <span className="ml-2 text-xs text-slate-400">历史待清理</span>}</li>)}</ul>
      <p className="mt-4 rounded-xl bg-rose-50 p-3 text-sm leading-6 text-rose-700">这些知识点的关联关系、学习状态、历史练习和相关会话记录将一并删除，无法恢复。</p>
      {error && <div role="alert" className="mt-4 text-sm text-rose-700"><p>{error}</p><button type="button" disabled={deleting} onClick={onReload} className="mt-2 underline disabled:opacity-40">刷新目录</button></div>}
    </div>
    <footer className="flex shrink-0 flex-wrap justify-end gap-3 border-t border-slate-100 px-5 py-4">
      <button ref={cancel} type="button" disabled={deleting} onClick={onCancel} className={actionClass}>取消</button>
      <button type="button" disabled={deleting} onClick={() => void remove()} className="rounded-xl bg-rose-600 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-700 disabled:opacity-40">{deleting ? "正在删除…" : "确认永久删除章节"}</button>
    </footer>
  </dialog>;
}
