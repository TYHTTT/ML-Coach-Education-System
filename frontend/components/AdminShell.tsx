"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import { useAdmin } from "@/components/AdminProvider";

export default function AdminShell({ children }: { children: ReactNode }) {
  const { logout } = useAdmin();
  const pathname = usePathname();
  const [leaving, setLeaving] = useState(false);
  async function signOut() {
    setLeaving(true);
    try { await logout(); } catch { /* The local session has been cleared. */ }
    finally { setLeaving(false); }
  }
  return <main className="min-h-svh bg-canvas">
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-6">
        <Link href="/admin" className="font-bold text-slate-900">管理后台</Link>
        <nav aria-label="后台导航" className="order-3 flex w-full gap-2 sm:order-none sm:w-auto">
          {[{ href: "/admin", label: "概览" }, { href: "/admin/courses", label: "课程管理" }].map((item) => <Link key={item.href} href={item.href} aria-current={pathname === item.href ? "page" : undefined} className={`rounded-xl px-4 py-2 text-sm font-semibold ${pathname === item.href ? "bg-indigo-50 text-indigo-700" : "text-slate-500 hover:bg-slate-50"}`}>{item.label}</Link>)}
        </nav>
        <div className="flex items-center gap-4 text-sm"><Link href="/learn" className="text-slate-500 hover:text-indigo-700">学生端</Link><button type="button" disabled={leaving} onClick={() => void signOut()} className="rounded-xl border border-slate-200 px-3 py-2 font-semibold text-slate-600 hover:border-rose-200 hover:text-rose-700 disabled:opacity-60">{leaving ? "正在退出…" : "退出管理后台"}</button></div>
      </div>
    </header>
    {children}
  </main>;
}
