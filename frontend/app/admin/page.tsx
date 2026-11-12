"use client";

import Link from "next/link";
import { useAdmin } from "@/components/AdminProvider";

export default function AdminHomePage() {
  const { admin } = useAdmin();
  if (!admin) return null;

  return <>
    <section aria-label="管理员账户" className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-12">
      <div className="mb-7 flex flex-wrap items-center justify-between gap-4"><h1 className="text-2xl font-bold text-slate-900">管理后台</h1><Link href="/admin/courses" className="rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700">管理课程</Link></div>
      <div className="max-w-2xl rounded-3xl border border-slate-200 bg-white p-6 sm:p-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-xl font-semibold text-slate-900">{admin.display_name}</h2>
          <span className="rounded-full bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-700">管理员</span>
        </div>
        <dl className="mt-7 grid gap-5 text-sm sm:grid-cols-2">
          <div><dt className="text-slate-500">用户名</dt><dd className="mt-1.5 break-all font-medium text-slate-800">{admin.username}</dd></div>
          <div><dt className="text-slate-500">账户状态</dt><dd className="mt-1.5 font-medium text-emerald-700">正常</dd></div>
          <div><dt className="text-slate-500">创建时间</dt><dd className="mt-1.5 text-slate-800">{new Date(admin.created_at).toLocaleString("zh-CN")}</dd></div>
          <div><dt className="text-slate-500">最近活动</dt><dd className="mt-1.5 text-slate-800">{new Date(admin.last_active_at).toLocaleString("zh-CN")}</dd></div>
        </dl>
      </div>
    </section>
  </>;
}
