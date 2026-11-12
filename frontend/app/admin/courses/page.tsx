"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAdmin } from "@/components/AdminProvider";
import { buttonClass, inputClass, message, primaryClass } from "@/components/AdminCourseForms";
import { getAdminCourses } from "@/lib/api";
import type { CourseList } from "@/lib/types";

export default function AdminCoursesPage() {
  const { withAdmin } = useAdmin();
  const router = useRouter();
  const [data, setData] = useState<CourseList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [page, setPage] = useState(1);
  const [version, setVersion] = useState(0);
  const refresh = () => setVersion((value) => value + 1);
  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setLoading(true); setError("");
      try {
        const result = await withAdmin((token) => getAdminCourses(token, { q: query, status, page }, controller.signal));
        if (!controller.signal.aborted) setData(result);
      } catch (cause) { if (!controller.signal.aborted) setError(message(cause)); }
      finally { if (!controller.signal.aborted) setLoading(false); }
    }, 0);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [withAdmin, query, status, page, version]);

  return <section className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-10">
    <div className="flex flex-wrap items-center justify-between gap-4"><h1 className="text-2xl font-bold text-slate-900">课程管理</h1><Link href="/admin/courses/new-course" className={primaryClass}>新增课程</Link></div>
    <form aria-label="搜索课程" onSubmit={(event) => { event.preventDefault(); setQuery(search.trim()); setPage(1); }} className="mt-6 flex flex-wrap items-end gap-3">
      <label className="min-w-48 flex-1 text-sm text-slate-600">课程名称或标识<input name="search" value={search} onChange={(event) => setSearch(event.target.value)} maxLength={100} className={inputClass} placeholder="搜索课程" /></label>
      <label className="text-sm text-slate-600">状态<select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }} className={inputClass}><option value="all">全部</option><option value="active">已启用</option><option value="inactive">已停用</option></select></label>
      <button type="submit" className={buttonClass}>搜索</button><button type="button" onClick={refresh} className={buttonClass}>刷新</button>
    </form>
    {error && <div role="alert" className="mt-5 flex items-start justify-between gap-3 rounded-xl bg-rose-50 p-3 text-sm text-rose-700"><p>{error}</p><button type="button" onClick={refresh} className="shrink-0 underline">重试</button></div>}
    <div className="mt-6 overflow-hidden rounded-3xl border border-slate-200 bg-white">
      {loading ? <p role="status" className="p-8 text-center text-sm text-slate-500">正在加载课程…</p> : data && data.items.length ? <div className="overflow-x-auto"><table className="w-full text-left text-sm">
        <thead className="bg-slate-50 text-slate-500"><tr>{["课程", "知识点", "状态", "排序"].map((title) => <th key={title} scope="col" className="whitespace-nowrap px-5 py-4 font-medium">{title}</th>)}</tr></thead>
        <tbody className="divide-y divide-slate-100">{data.items.map((course) => {
          const href = `/admin/courses/${encodeURIComponent(course.id)}`;
          return <tr key={course.id} className="group cursor-pointer transition-colors hover:bg-indigo-50/60 focus-within:bg-indigo-50/60" onClick={(event) => {
            if (event.defaultPrevented || (event.target as HTMLElement).closest("a")) return;
            if (event.ctrlKey || event.metaKey) window.open(href, "_blank", "noopener,noreferrer");
            else router.push(href);
          }}>
            <td className="min-w-48 p-0"><Link href={href} aria-label={`查看${course.title}详情`} className="block px-5 py-5 outline-offset-[-4px] focus-visible:outline-2 focus-visible:outline-indigo-500"><p className="font-semibold text-slate-900 group-hover:text-indigo-700">{course.title}</p><p className="mt-1 break-all text-xs text-slate-400">{course.id}</p></Link></td>
            <td className="px-5 py-5 tabular-nums text-slate-600">{course.topic_count}</td>
            <td className="whitespace-nowrap px-5 py-5"><span className={`rounded-full px-2.5 py-1 text-xs font-medium ${course.active ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>{course.active ? "已启用" : "已停用"}</span></td>
            <td className="px-5 py-5 tabular-nums text-slate-600">{course.sort_order}</td>
          </tr>;
        })}</tbody>
      </table></div> : <p className="p-10 text-center text-sm text-slate-500">{error ? "课程列表暂时无法加载。" : query || status !== "all" ? "没有匹配的课程。" : "暂无课程，点击“新增课程”开始创建。"}</p>}
      {data && !loading && <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 px-5 py-4 text-sm text-slate-500"><span>共 {data.total} 门课程</span><div className="flex items-center gap-3"><button type="button" disabled={page <= 1} onClick={() => setPage((value) => value - 1)} className={buttonClass}>上一页</button><span>第 {page} 页</span><button type="button" disabled={page * data.page_size >= data.total} onClick={() => setPage((value) => value + 1)} className={buttonClass}>下一页</button></div></div>}
    </div>
  </section>;
}
