"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAdmin } from "@/components/AdminProvider";
import { CourseEditor, DeleteDialog, buttonClass, message } from "@/components/AdminCourseForms";
import CourseTopicsManager from "@/components/CourseTopicsManager";
import { ApiError, deleteCourse, getAdminCourse, updateCourse } from "@/lib/api";
import type { CourseDetail, CourseInput } from "@/lib/types";

function CourseDetails({ courseId }: { courseId: string }) {
  const { withAdmin } = useAdmin();
  const router = useRouter();
  const [course, setCourse] = useState<CourseDetail | null>(null);
  const [error, setError] = useState("");
  const [notFound, setNotFound] = useState(false);
  const [notice, setNotice] = useState("");
  const [version, setVersion] = useState(0);
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [topicBusy, setTopicBusy] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setError(""); setNotFound(false);
      try {
        const detail = await withAdmin((token) => getAdminCourse(token, courseId, controller.signal));
        if (!controller.signal.aborted) setCourse(detail);
      } catch (cause) {
        if (!controller.signal.aborted) { setError(message(cause)); setNotFound(cause instanceof ApiError && cause.status === 404); }
      }
    }, 0);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [courseId, withAdmin, version]);
  async function save(values: CourseInput) {
    const { id, ...changes } = values;
    const result = await withAdmin((token) => updateCourse(token, id, changes));
    setCourse((previous) => previous ? { ...previous, ...result } : null);
    setEditing(false); setNotice("课程信息已保存。");
  }
  async function remove() {
    await withAdmin((token) => deleteCourse(token, courseId));
    router.replace("/admin/courses");
  }
  return <section className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-10">
    <Link href="/admin/courses" className="text-sm text-slate-500 hover:text-indigo-700">← 返回课程管理</Link>
    {error && <div role="alert" className="mt-5 rounded-xl bg-rose-50 p-4 text-sm text-rose-700"><p>{notFound ? "课程不存在或已删除。" : error}</p>{!notFound && <button type="button" className="mt-2 underline" onClick={() => setVersion((v) => v + 1)}>重新加载</button>}</div>}
    {!course && !error && <p role="status" className="py-10 text-slate-500">正在加载课程详情…</p>}
    {course && <>
      <div className="mt-5 flex flex-wrap items-center justify-between gap-4"><div><h1 className="break-words text-2xl font-bold text-slate-900">{course.title}</h1><p className="mt-2 break-all text-xs text-slate-400">{course.id}</p></div><span className={`rounded-full px-3 py-1.5 text-sm font-medium ${course.active ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>{course.active ? "已启用" : "已停用"}</span></div>
      {notice && <p role="status" className="mt-4 text-sm text-emerald-700">{notice}</p>}
      {editing ? <CourseEditor course={course} onSave={save} onCancel={() => setEditing(false)} /> : <section aria-label="课程基本信息" className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-lg font-bold text-slate-900">基本信息</h2><div className="flex gap-2"><button type="button" disabled={topicBusy || deleting} onClick={() => { setEditing(true); setNotice(""); }} className={buttonClass}>编辑课程</button><button type="button" disabled={topicBusy || deleting} onClick={() => setDeleting(true)} className={`${buttonClass} text-rose-700 hover:border-rose-300`}>删除课程</button></div></div>
        <p className="mt-4 whitespace-pre-wrap break-words text-sm leading-7 text-slate-600">{course.description || "暂无课程简介"}</p>
        <dl className="mt-5 flex flex-wrap gap-x-8 gap-y-3 text-xs text-slate-500"><div className="flex gap-2"><dt>展示排序</dt><dd>{course.sort_order}</dd></div><div className="flex gap-2"><dt>最近修改</dt><dd>{new Date(course.updated_at).toLocaleString("zh-CN")}</dd></div></dl>
      </section>}
      {!course.active && <p className="mt-4 text-sm text-amber-700">课程已停用，可继续编辑和编排，启用后向学生展示。</p>}
      <fieldset disabled={editing || deleting} className="min-w-0"><CourseTopicsManager courseId={courseId} onInteractionChange={setTopicBusy} /></fieldset>
      {deleting && <DeleteDialog course={course} onDelete={remove} onCancel={() => setDeleting(false)} />}
    </>}
  </section>;
}

export default function CourseDetailPage() {
  const { courseId } = useParams<{ courseId: string }>();
  return <CourseDetails key={courseId} courseId={courseId} />;
}
