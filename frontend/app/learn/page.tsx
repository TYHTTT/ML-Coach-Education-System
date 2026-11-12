import Link from "next/link";
import { ArrowRightIcon } from "@/components/Icons";
import { COURSE_META, COURSES, type Course } from "@/lib/types";

const COURSE_DETAILS: Record<Course, { stages: string; cue: string; gradient: string; ring: string }> = {
  machine_learning: {
    stages: "7 个阶段",
    cue: "从基础概念、模型训练到机器学习工程",
    gradient: "from-indigo-600 to-violet-600",
    ring: "group-hover:border-indigo-300 group-hover:shadow-indigo-100",
  },
  advanced_mathematics: {
    stages: "5 个阶段",
    cue: "从函数极限、一元微积分到多元积分",
    gradient: "from-cyan-600 to-sky-600",
    ring: "group-hover:border-cyan-300 group-hover:shadow-cyan-100",
  },
  linear_algebra: { stages: "数学准备", cue: "机器学习所需的向量、矩阵与投影基础", gradient: "from-violet-600 to-purple-600", ring: "group-hover:border-violet-300" },
  probability_statistics: { stages: "数学准备", cue: "从条件概率、期望与方差到似然", gradient: "from-amber-600 to-orange-600", ring: "group-hover:border-amber-300" },
};

export default function LearnHomePage() {
  return (
    <div className="min-h-[calc(100svh-65px)] bg-canvas">
      <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 sm:py-14 lg:px-8">
        <header>
          <h1 className="text-2xl font-bold tracking-tight text-slate-950">课程学习</h1>
        </header>

        <section className="mt-6 grid gap-5 md:grid-cols-2" aria-label="选择课程">
          {COURSES.map((course) => {
            const meta = COURSE_META[course];
            const detail = COURSE_DETAILS[course];
            return (
              <Link
                key={course}
                href={`/learn/${course}`}
                className={`group relative overflow-hidden rounded-3xl border border-slate-200 bg-white p-6 shadow-soft transition duration-200 hover:-translate-y-0.5 hover:shadow-xl ${detail.ring} focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 sm:p-7`}
              >
                <div className="flex items-start justify-between gap-5">
                  <span className={`grid size-14 place-items-center rounded-2xl bg-gradient-to-br ${detail.gradient} text-xl font-bold text-white shadow-lg`}>
                    {meta.shortLabel}
                  </span>
                  <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[11px] font-semibold text-slate-500">
                    {detail.stages}
                  </span>
                </div>
                <h2 className="mt-6 text-xl font-bold tracking-tight text-slate-900">{meta.label}</h2>
                <p className="mt-2 text-sm leading-6 text-slate-500">{detail.cue}</p>
                <div className="mt-7 flex items-center gap-2 text-sm font-semibold text-indigo-700">
                  查看学习路径
                  <ArrowRightIcon className="size-4 transition-transform group-hover:translate-x-1" />
                </div>
              </Link>
            );
          })}
        </section>

      </div>
    </div>
  );
}
