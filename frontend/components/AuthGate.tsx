"use client";

import { type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { useAdmin } from "@/components/AdminProvider";
import LoginForm from "@/components/LoginForm";
import { useStudent } from "@/components/StudentProvider";

export default function AuthGate({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return pathname === "/admin" || pathname.startsWith("/admin/") ? (
    <AdminGate>{children}</AdminGate>
  ) : (
    <StudentGate>{children}</StudentGate>
  );
}

function StudentGate({ children }: { children: ReactNode }) {
  const { status, error } = useStudent();
  if (status === "ready") return <>{children}</>;
  if (status === "initializing")
    return (
      <main className="grid min-h-svh place-items-center bg-canvas text-sm text-slate-500">
        正在恢复登录状态...
      </main>
    );
  return <LoginForm error={error} />;
}

function AdminGate({ children }: { children: ReactNode }) {
  const { status, error, retry } = useAdmin();
  if (status === "ready") return <>{children}</>;
  if (status === "initializing")
    return (
      <main className="grid min-h-svh place-items-center bg-canvas text-sm text-slate-500">
        正在验证管理员身份…
      </main>
    );
  if (status !== "error")
    return <LoginForm initialRole="admin" error={error} />;
  return (
    <main className="grid min-h-svh place-items-center bg-canvas p-6">
      <section className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-8">
        <h1 className="text-xl font-semibold text-slate-900">
          管理员身份暂时无法验证
        </h1>
        <p role="alert" className="mt-3 text-sm text-slate-600">
          {error}
        </p>
        <button
          type="button"
          onClick={retry}
          className="mt-6 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white"
        >
          重试
        </button>
      </section>
    </main>
  );
}
