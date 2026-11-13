"use client";

import { useEffect, useState } from "react";
import { useAdmin } from "@/components/AdminProvider";
import { getRelatedTopicCandidates, type RelatedTopic, type RelatedTopicCandidates } from "@/lib/topic-management";

const inputClass = "w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus:border-indigo-500";
export default function RelatedTopicsPicker({ topicId, courseId, selected, initialTopics, onChange }: {
  topicId?: string; courseId: string; selected: string[]; initialTopics: RelatedTopic[]; onChange: (ids: string[]) => void;
}) {
  const { withAdmin } = useAdmin();
  const [query, setQuery] = useState("");
  const [course, setCourse] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<RelatedTopicCandidates | null>(null);
  const [known, setKnown] = useState<Record<string, RelatedTopic>>(() => Object.fromEntries(initialTopics.map((topic) => [topic.id, topic])));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setLoading(true); setError("");
      try {
        const result = await withAdmin((token) => getRelatedTopicCandidates(token, { q: query.trim(), course, exclude: topicId, page }, controller.signal));
        if (controller.signal.aborted) return;
        setKnown((previous) => ({ ...previous, ...Object.fromEntries(result.items.map((topic) => [topic.id, topic])) }));
        setData(result);
      } catch (cause) {
        if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "相关知识点加载失败。");
      } finally { if (!controller.signal.aborted) setLoading(false); }
    }, 200);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [withAdmin, query, course, page, topicId, version]);

  return <div className="min-w-0 space-y-3 sm:col-span-2" role="group" aria-label="相关知识点">
    <div className="flex items-center justify-between gap-3"><h3 className="text-sm font-medium text-slate-700">相关知识点</h3><span className="text-xs tabular-nums text-slate-400">已选 {selected.length} 个</span></div>
    <p className="text-xs leading-5 text-slate-500">可选择本课程或其他课程的知识点。关联会双向保存，仅用于描述知识联系。</p>
    {!!selected.length && <ul aria-label="已选相关知识点" className="flex max-h-36 flex-wrap gap-2 overflow-y-auto overscroll-contain">{selected.map((id) => {
      const topic = known[id];
      return <li key={id} className={`flex min-w-0 max-w-full items-center gap-1 rounded-lg px-2 py-1 text-xs ${topic?.available === false ? "bg-amber-50 text-amber-800" : "bg-indigo-50 text-indigo-700"}`}>
        <span className="min-w-0 break-words">{topic?.course_title ? `${topic.course_title} / ` : ""}{topic?.title ?? id}{topic?.available === false ? "（已不可用）" : ""}</span>
        <button type="button" aria-label={`移除关联${topic?.title ?? id}`} onClick={() => onChange(selected.filter((key) => key !== id))} className="flex size-6 shrink-0 items-center justify-center rounded hover:bg-indigo-100">×</button>
      </li>;
    })}</ul>}
    <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <input type="search" aria-label="搜索相关知识点" maxLength={100} placeholder="搜索名称、ID 或课程" value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} onKeyDown={(event) => { if (event.key === "Enter") event.preventDefault(); }} className={inputClass} />
      <select aria-label="筛选相关知识点课程" value={course} onChange={(event) => { setCourse(event.target.value); setPage(1); }} className={inputClass}>
        <option value="">全部课程</option>{data?.courses.map((entry) => <option key={entry.id} value={entry.id}>{entry.id === courseId ? "本课程：" : ""}{entry.title}{entry.active ? "" : "（停用）"}</option>)}
      </select>
    </div>
    <div className="max-h-52 overflow-y-auto overscroll-contain rounded-xl border border-slate-200">
      {loading ? <p role="status" className="p-4 text-sm text-slate-400">正在加载相关知识点…</p> : error ? <p role="alert" className="p-4 text-sm text-rose-700">{error}<button type="button" onClick={() => setVersion((value) => value + 1)} className="ml-2 underline">重试</button></p> : data?.items.length ? <ul aria-label="可选相关知识点" className="divide-y divide-slate-100">{data.items.map((topic) => <li key={topic.id}>
        <label className="flex cursor-pointer items-start gap-3 px-3 py-2.5 hover:bg-slate-50">
          <input type="checkbox" aria-label={`关联${topic.title}（${topic.course_title}）`} checked={selected.includes(topic.id)} onChange={(event) => onChange(event.target.checked ? [...selected, topic.id] : selected.filter((id) => id !== topic.id))} className="mt-1 size-4 shrink-0 accent-indigo-600" />
          <span className="min-w-0"><span className="block break-words text-sm text-slate-700">{topic.title}<span className="ml-2 text-xs text-slate-400">{topic.course_title}{topic.course_active ? "" : " · 课程停用"}</span></span><span className="mt-0.5 block break-all font-mono text-[11px] text-slate-400">{topic.id}</span></span>
        </label>
      </li>)}</ul> : <p className="p-4 text-sm text-slate-400">没有匹配的知识点</p>}
    </div>
    {data && !loading && !error && data.total > data.page_size && <div className="flex items-center justify-between gap-2 text-xs text-slate-500"><span>共 {data.total} 个 · 第 {page} 页</span><div className="flex gap-3"><button type="button" disabled={page <= 1} onClick={() => setPage((value) => value - 1)} className="text-indigo-700 disabled:text-slate-300">上一页</button><button type="button" disabled={page * data.page_size >= data.total} onClick={() => setPage((value) => value + 1)} className="text-indigo-700 disabled:text-slate-300">下一页</button></div></div>}
  </div>;
}
