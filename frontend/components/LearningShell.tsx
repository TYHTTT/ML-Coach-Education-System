"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import {
  BookIcon,
  GearIcon,
  SparklesIcon,
  TargetIcon,
} from "@/components/Icons";
import { useStudent } from "@/components/StudentProvider";

const NAV_ITEMS = [
  { href: "/?view=chat", label: "自由问答", icon: SparklesIcon },
  { href: "/learn", label: "课程学习", icon: TargetIcon },
  { href: "/settings", label: "设置", icon: GearIcon },
];

export default function LearningShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { student, logout } = useStudent();

  return (
    <main className="min-h-svh bg-canvas">
      <header className="sticky top-0 z-30 border-b border-slate-200/80 bg-white/90 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 py-2 sm:px-6 lg:px-8">
          <Link
            href="/learn"
            className="flex min-w-0 items-center gap-3 rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2"
          >
            <span className="grid size-10 shrink-0 place-items-center rounded-2xl bg-gradient-to-br from-indigo-600 to-violet-600 text-white shadow-md shadow-indigo-200">
              <BookIcon className="size-5" />
            </span>
            <span className="min-w-0">
              <span className="block truncate text-sm font-bold tracking-tight text-slate-900 sm:text-base">Course Coach</span>
              <span className="hidden text-[11px] text-slate-400 sm:block">可测量学习闭环</span>
            </span>
          </Link>

          <nav className="flex items-center gap-1 rounded-2xl border border-slate-200 bg-slate-50/80 p-1" aria-label="主导航">
            {NAV_ITEMS.map((item) => {
              const active = item.href.startsWith("/?")
                ? pathname === "/"
                : item.href === "/learn"
                  ? pathname.startsWith("/learn")
                  : pathname === item.href;
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={`inline-flex items-center gap-2 rounded-xl px-2.5 py-2 text-xs font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 sm:px-3 ${
                    active
                      ? "bg-white text-indigo-700 shadow-sm"
                      : "text-slate-500 hover:bg-white/70 hover:text-slate-800"
                  }`}
                >
                  <Icon className="size-4" />
                  <span className="hidden md:inline">{item.label}</span>
                </Link>
              );
            })}
          </nav>

          <div className="hidden min-w-28 items-center justify-end gap-3 sm:flex">
            <span className="max-w-28 truncate text-xs font-semibold text-slate-600" title={student?.username}>{student?.display_name}</span>
            <button type="button" onClick={() => void logout()} className="text-xs font-semibold text-slate-500 hover:text-slate-900">退出</button>
          </div>
        </div>
      </header>

      {children}
    </main>
  );
}
