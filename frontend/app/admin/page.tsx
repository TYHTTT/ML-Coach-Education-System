"use client";

import Link from "next/link";
import { useState } from "react";
import { useAdmin } from "@/components/AdminProvider";

export default function AdminHomePage() {
  const { admin, logout } = useAdmin();
  const [leaving, setLeaving] = useState(false);
  if (!admin) return null;

  async function signOut() {
    setLeaving(true);
    try { await logout(); } catch { /* The local administrator session has already been cleared. */ }
    finally { setLeaving(false); }
  }

  return <main className="min-h-svh bg-canvas">
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-5 sm:px-6">
        <h1 className="text-lg font-bold text-slate-900">管理后台</h1>
        <div className="flex items-center gap-4 text-sm">
          <Link href="/learn" className="text-slate-500 hover:text-indigo-700">学生端</Link>
          <button type="button" disabled={leaving} onClick={() => void signOut()} className="rounded-xl border border-slate-200 px-3 py-2 font-semibold text-slate-600 hover:border-rose-200 hover:text-rose-700 disabled:opacity-60">{leaving ? "正在退出…" : "退出管理后台"}</button>
        </div>
      </div>
    </header>
    <section aria-label="管理员账户" className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-12">
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
  </main>;
}
