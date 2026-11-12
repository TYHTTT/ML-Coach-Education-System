"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAdmin } from "@/components/AdminProvider";
import { CourseEditor } from "@/components/AdminCourseForms";
import { createCourse } from "@/lib/api";
import type { CourseInput } from "@/lib/types";

export default function NewCoursePage() {
  const { withAdmin } = useAdmin();
  const router = useRouter();
  async function save(values: CourseInput) {
    const course = await withAdmin((token) => createCourse(token, values));
    router.replace(`/admin/courses/${encodeURIComponent(course.id)}`);
  }
  return <section className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-10">
    <Link href="/admin/courses" className="text-sm text-slate-500 hover:text-indigo-700">← 返回课程管理</Link>
    <h1 className="mt-5 text-2xl font-bold text-slate-900">新增课程</h1>
    <CourseEditor course={null} onSave={save} onCancel={() => router.push("/admin/courses")} />
  </section>;
}
