"use client";

import LearningShell from "@/components/LearningShell";
import { useTheme } from "@/components/ThemeProvider";

export default function SettingsPage() {
  const { theme, setTheme } = useTheme();
  return (
    <LearningShell>
      <section className="mx-auto max-w-3xl px-4 py-10 sm:px-6 lg:px-8">
        <div className="border-b border-slate-200 pb-6">
          <h1 className="text-2xl font-bold text-slate-900">设置</h1>
          <p className="mt-2 text-sm text-slate-500">
            调整 Course Coach 的显示偏好。
          </p>
        </div>

        <div className="mt-8 border border-slate-200 bg-white p-5 shadow-soft sm:p-6">
          <h2 className="text-base font-bold text-slate-900">外观</h2>
          <div className="mt-5 flex items-center justify-between gap-6">
            <div>
              <p className="text-sm font-semibold text-slate-800">界面主题</p>
              <p className="mt-1 text-sm text-slate-500">
                选择浅色或深色显示模式。
              </p>
            </div>
            <div
              className="inline-flex shrink-0 rounded-lg border border-slate-200 bg-slate-50 p-1"
              role="group"
              aria-label="界面主题"
            >
              {(["light", "dark"] as const).map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => setTheme(option)}
                  aria-pressed={theme === option}
                  className={`rounded-md px-3 py-2 text-sm font-semibold transition ${theme === option ? "bg-white text-indigo-700 shadow-sm" : "text-slate-500 hover:text-slate-800"}`}
                >
                  {option === "light" ? "Light" : "Dark"}
                </button>
              ))}
            </div>
          </div>
        </div>

        <p className="mt-6 text-sm text-slate-500">
          AI 辅导由 Dify Agent 提供，课程资料由 Dify 统一管理。
        </p>
      </section>
    </LearningShell>
  );
}
