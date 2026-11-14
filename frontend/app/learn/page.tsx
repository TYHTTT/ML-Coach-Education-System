"use client";

import Link from "next/link";
import { ArrowRightIcon } from "@/components/Icons";
import { useCourseCatalog } from "@/components/CourseCatalogProvider";
import { COURSE_META } from "@/lib/types";

export default function LearnHomePage() {
  const { courses, loading, error, reload } = useCourseCatalog();
  return (
    <div className="min-h-[calc(100svh-65px)] bg-canvas">
      <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 sm:py-14 lg:px-8">
        <h1 className="text-2xl font-bold tracking-tight text-slate-950">
          课程学习
        </h1>
        {loading ? (
          <p role="status" className="mt-8 text-sm text-slate-500">
            正在加载课程…
          </p>
        ) : error ? (
          <div
            role="alert"
            className="mt-6 rounded-2xl bg-rose-50 p-5 text-sm text-rose-700"
          >
            <p>{error}</p>
            <button
              type="button"
              onClick={reload}
              className="mt-3 font-semibold underline"
            >
              重试
            </button>
          </div>
        ) : courses.length ? (
          <section
            className="mt-6 grid gap-5 md:grid-cols-2"
            aria-label="选择课程"
          >
            {courses.map((course) => (
              <Link
                key={course.id}
                href={`/learn/${course.id}`}
                className="group rounded-3xl border border-slate-200 bg-white p-6 shadow-soft transition hover:border-indigo-300 hover:shadow-lg sm:p-7"
              >
                <div className="flex items-start justify-between gap-5">
                  <span className="grid size-14 place-items-center rounded-2xl bg-indigo-600 text-xl font-bold text-white">
                    {COURSE_META[course.id]?.shortLabel ??
                      course.title.slice(0, 2)}
                  </span>
                  <span className="rounded-full bg-slate-50 px-3 py-1 text-xs text-slate-500">
                    {course.topic_count} 个知识点
                  </span>
                </div>
                <h2 className="mt-6 text-xl font-bold text-slate-900">
                  {course.title}
                </h2>
                {course.description && (
                  <p className="mt-2 text-sm leading-6 text-slate-500">
                    {course.description}
                  </p>
                )}
                <span className="mt-7 inline-flex items-center gap-2 text-sm font-semibold text-indigo-700">
                  查看学习路径
                  <ArrowRightIcon className="size-4 transition-transform group-hover:translate-x-1" />
                </span>
              </Link>
            ))}
          </section>
        ) : (
          <p className="mt-8 rounded-2xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-500">
            暂无可学习的课程。
          </p>
        )}
      </div>
    </div>
  );
}
