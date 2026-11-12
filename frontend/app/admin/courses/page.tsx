"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { useAdmin } from "@/components/AdminProvider";
import { createCourse, deleteCourse, getAdminCourse, getAdminCourses, updateCourse } from "@/lib/api";
import type { CourseDetail, CourseInput, CourseList, CourseRecord } from "@/lib/types";

const inputClass = "mt-1.5 w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 focus:border-indigo-500";
const buttonClass = "rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-600 hover:border-indigo-300 disabled:cursor-not-allowed disabled:opacity-50";
const primaryClass = "rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-wait disabled:opacity-50";
function message(error: unknown) { return error instanceof Error ? error.message : "操作失败，请重试。"; }

function CourseEditor({ course, onSave, onCancel }: {
  course: CourseRecord | null;
  onSave: (values: CourseInput) => Promise<void>;
  onCancel: () => void;
}) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const firstInput = useRef<HTMLInputElement>(null);
  useEffect(() => { firstInput.current?.focus(); }, []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setSaving(true); setError("");
    try {
      await onSave({ id: String(data.get("id")), title: String(data.get("title")).trim(), description: String(data.get("description")).trim(), sort_order: Number(data.get("sort_order")), active: data.get("active") === "on" });
    } catch (cause) { setError(message(cause)); }
    finally { setSaving(false); }
  }
  return <section aria-label={course ? "编辑课程" : "新增课程"} className="mt-6 rounded-3xl border border-indigo-200 bg-white p-5 sm:p-6">
    <h2 className="text-lg font-bold text-slate-900">{course ? "编辑课程" : "新增课程"}</h2>
    <form aria-label="课程信息" onSubmit={submit} className="mt-5">
      <fieldset disabled={saving} className="grid gap-4 sm:grid-cols-2">
        <label className="text-sm font-medium text-slate-700">课程名称<input ref={firstInput} required name="title" maxLength={100} defaultValue={course?.title} className={inputClass} /></label>
        <label className="text-sm font-medium text-slate-700">课程标识<input required name="id" minLength={2} maxLength={64} pattern="[a-z][a-z0-9_]{1,63}" placeholder="例如 data_structures" readOnly={Boolean(course)} defaultValue={course?.id} className={`${inputClass} read-only:bg-slate-50 read-only:text-slate-500`} /><span className="mt-1 block text-xs font-normal text-slate-500">小写字母、数字和下划线，创建后不可修改。</span></label>
        <label className="text-sm font-medium text-slate-700 sm:col-span-2">课程简介<textarea name="description" maxLength={1000} rows={3} defaultValue={course?.description} className={`${inputClass} resize-y`} /></label>
        <label className="text-sm font-medium text-slate-700">排序<input required type="number" name="sort_order" min={0} max={99999} step={1} defaultValue={course?.sort_order ?? 0} className={inputClass} /><span className="mt-1 block text-xs font-normal text-slate-500">数值越小，展示越靠前。</span></label>
        <label className="flex items-center gap-2 self-center text-sm font-medium text-slate-700"><input name="active" type="checkbox" defaultChecked={course?.active ?? true} className="size-4 accent-indigo-600" />在学生端展示</label>
      </fieldset>
      {error && <p role="alert" className="mt-4 rounded-xl bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}
      <div className="mt-5 flex justify-end gap-3"><button disabled={saving} type="button" onClick={onCancel} className={buttonClass}>取消</button><button disabled={saving} type="submit" className={primaryClass}>{saving ? "正在保存…" : "保存课程"}</button></div>
    </form>
  </section>;
}

function DeleteDialog({ course, onDelete, onCancel }: { course: CourseRecord; onDelete: () => Promise<void>; onCancel: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { const dialog = ref.current; dialog?.showModal(); return () => dialog?.close(); }, []);
  async function remove() {
    setDeleting(true); setError("");
    try { await onDelete(); } catch (cause) { setError(message(cause)); }
    finally { setDeleting(false); }
  }
  return <dialog ref={ref} aria-labelledby="delete-course-heading" onCancel={(event) => { if (deleting) event.preventDefault(); else onCancel(); }} className="m-auto w-[calc(100%-2rem)] max-w-md rounded-3xl border border-slate-200 bg-white p-6 shadow-xl backdrop:bg-slate-950/40">
    <h2 id="delete-course-heading" className="text-lg font-bold text-slate-900">删除课程</h2>
    <p className="mt-4 break-words text-sm leading-6 text-slate-600">确定删除“{course.title}”？删除后课程将从列表移除，已有知识点和学习记录会保留。</p>
    {error && <p role="alert" className="mt-4 text-sm text-rose-700">{error}</p>}
    <div className="mt-6 flex justify-end gap-3"><button disabled={deleting} type="button" onClick={onCancel} className={buttonClass}>取消</button><button disabled={deleting} type="button" onClick={() => void remove()} className="rounded-xl bg-rose-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-rose-700 disabled:opacity-50">{deleting ? "正在删除…" : "确认删除"}</button></div>
  </dialog>;
}

export default function AdminCoursesPage() {
  const { withAdmin } = useAdmin();
  const [data, setData] = useState<CourseList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [page, setPage] = useState(1);
  const [version, setVersion] = useState(0);
  const [editor, setEditor] = useState<CourseRecord | "new" | null>(null);
  const [detail, setDetail] = useState<CourseDetail | null>(null);
  const [deleting, setDeleting] = useState<CourseRecord | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const refresh = useCallback(() => setVersion((value) => value + 1), []);
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

  async function inspect(course: CourseRecord, edit: boolean) {
    setActionBusy(true); setError(""); setNotice("");
    try {
      const result = await withAdmin((token) => getAdminCourse(token, course.id));
      setDetail(edit ? null : result); setEditor(edit ? result : null);
    } catch (cause) { setError(message(cause)); }
    finally { setActionBusy(false); }
  }
  async function save(values: CourseInput) {
    if (editor && editor !== "new") {
      const { id, ...changes } = values;
      await withAdmin((token) => updateCourse(token, id, changes));
    } else { await withAdmin((token) => createCourse(token, values)); }
    setEditor(null); setNotice("课程已保存。"); refresh();
  }
  async function remove() {
    if (!deleting) return;
    await withAdmin((token) => deleteCourse(token, deleting.id));
    setDeleting(null); setEditor(null); setDetail(null); setNotice("课程已删除，已有学习数据已保留。");
    if (data?.items.length === 1 && page > 1) setPage((value) => value - 1);
    else refresh();
  }
  return <section className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-10">
    <div className="flex flex-wrap items-center justify-between gap-4"><h1 className="text-2xl font-bold text-slate-900">课程管理</h1><button type="button" onClick={() => { setEditor("new"); setDetail(null); setNotice(""); }} className={primaryClass}>新增课程</button></div>
    <form aria-label="搜索课程" onSubmit={(event) => { event.preventDefault(); setQuery(search.trim()); setPage(1); }} className="mt-6 flex flex-wrap items-end gap-3">
      <label className="min-w-48 flex-1 text-sm text-slate-600">课程名称或标识<input name="search" value={search} onChange={(event) => setSearch(event.target.value)} maxLength={100} className={inputClass} placeholder="搜索课程" /></label>
      <label className="text-sm text-slate-600">状态<select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }} className={inputClass}><option value="all">全部</option><option value="active">已启用</option><option value="inactive">已停用</option></select></label>
      <button type="submit" className={buttonClass}>搜索</button><button type="button" onClick={refresh} className={buttonClass}>刷新</button>
    </form>
    {notice && <p role="status" className="mt-5 rounded-xl bg-emerald-50 p-3 text-sm text-emerald-700">{notice}</p>}
    {error && <div role="alert" className="mt-5 flex items-start justify-between gap-3 rounded-xl bg-rose-50 p-3 text-sm text-rose-700"><p>{error}</p><button type="button" onClick={refresh} className="shrink-0 underline">重试</button></div>}
    {editor && <CourseEditor key={editor === "new" ? "new" : editor.id} course={editor === "new" ? null : editor} onSave={save} onCancel={() => setEditor(null)} />}
    {detail && <section aria-label="课程详情" className="mt-6 rounded-3xl border border-slate-200 bg-white p-5 sm:p-6">
      <div className="flex items-start justify-between gap-4"><div><h2 className="text-lg font-bold text-slate-900">{detail.title}</h2><p className="mt-1 break-all text-xs text-slate-500">{detail.id} · {detail.active ? "已启用" : "已停用"} · 排序 {detail.sort_order}</p></div><button type="button" onClick={() => setDetail(null)} className={buttonClass}>关闭详情</button></div>
      <p className="mt-4 whitespace-pre-wrap break-words text-sm text-slate-600">{detail.description || "暂无简介"}</p>
      <p className="mt-3 text-xs text-slate-400">最近修改：{new Date(detail.updated_at).toLocaleString("zh-CN")}</p>
      <h3 className="mt-6 text-sm font-semibold text-slate-800">课程知识点</h3>
      {detail.topics.length ? <ul className="mt-3 grid gap-2 sm:grid-cols-2">{detail.topics.map((topic) => <li key={topic.id} className="rounded-xl bg-slate-50 px-3 py-2 text-sm text-slate-700">{topic.title}<span className="ml-2 text-xs text-slate-400">{topic.stage_title}{topic.active ? "" : " · 已停用"}</span></li>)}</ul> : <p className="mt-3 text-sm text-slate-500">当前课程暂无知识点。</p>}
    </section>}
    <div className="mt-6 overflow-hidden rounded-3xl border border-slate-200 bg-white">
      {loading ? <p role="status" className="p-8 text-center text-sm text-slate-500">正在加载课程…</p> : data && data.items.length ? <div className="overflow-x-auto"><table className="w-full text-left text-sm">
        <thead className="bg-slate-50 text-slate-500"><tr>{["课程", "知识点", "状态", "排序", "操作"].map((title) => <th key={title} scope="col" className="whitespace-nowrap px-5 py-4 font-medium">{title}</th>)}</tr></thead>
        <tbody className="divide-y divide-slate-100">{data.items.map((course) => <tr key={course.id}><td className="min-w-52 px-5 py-4"><p className="font-semibold text-slate-900">{course.title}</p><p className="mt-1 break-all text-xs text-slate-400">{course.id}</p></td><td className="px-5 py-4 tabular-nums text-slate-600">{course.topic_count}</td><td className="whitespace-nowrap px-5 py-4"><span className={`rounded-full px-2.5 py-1 text-xs font-medium ${course.active ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>{course.active ? "已启用" : "已停用"}</span></td><td className="px-5 py-4 tabular-nums text-slate-600">{course.sort_order}</td><td className="px-5 py-4"><div className="flex items-center gap-4 whitespace-nowrap"><button type="button" disabled={actionBusy} aria-label={`查看${course.title}`} onClick={() => void inspect(course, false)} className="font-medium text-indigo-700 disabled:opacity-50">查看</button><button type="button" disabled={actionBusy} aria-label={`编辑${course.title}`} onClick={() => void inspect(course, true)} className="font-medium text-indigo-700 disabled:opacity-50">编辑</button><button type="button" disabled={actionBusy} aria-label={`删除${course.title}`} onClick={() => setDeleting(course)} className="font-medium text-rose-700 disabled:opacity-50">删除</button></div></td></tr>)}</tbody>
      </table></div> : <p className="p-10 text-center text-sm text-slate-500">{error ? "课程列表暂时无法加载。" : query || status !== "all" ? "没有匹配的课程。" : "暂无课程，点击“新增课程”开始创建。"}</p>}
      {data && !loading && <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 px-5 py-4 text-sm text-slate-500"><span>共 {data.total} 门课程</span><div className="flex items-center gap-3"><button type="button" disabled={page <= 1} onClick={() => setPage((value) => value - 1)} className={buttonClass}>上一页</button><span>第 {page} 页</span><button type="button" disabled={page * data.page_size >= data.total} onClick={() => setPage((value) => value + 1)} className={buttonClass}>下一页</button></div></div>}
    </div>
    {deleting && <DeleteDialog course={deleting} onDelete={remove} onCancel={() => setDeleting(null)} />}
  </section>;
}
