import type { TopicStatus } from "@/lib/types";
import { percent, statusMeta } from "@/lib/learning";

export function TopicStatusBadge({ status }: { status: TopicStatus | string }) {
  const meta = statusMeta(status);
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${meta.badge}`}
    >
      <span aria-hidden="true">{meta.symbol}</span>
      {meta.label}
    </span>
  );
}

export function MasteryBar({
  value,
  label = "掌握度",
  compact = false,
}: {
  value?: number | null;
  label?: string;
  compact?: boolean;
}) {
  const evaluated =
    value !== null && value !== undefined && Number.isFinite(value);
  const bounded = evaluated ? Math.min(1, Math.max(0, value)) : 0;
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between gap-3 text-[11px]">
        <span className="font-medium text-slate-500">{label}</span>
        <span
          className={`font-semibold tabular-nums ${evaluated ? "text-slate-700" : "text-slate-400"}`}
        >
          {percent(value)}
        </span>
      </div>
      <div
        className={`${compact ? "h-1.5" : "h-2"} overflow-hidden rounded-full bg-slate-100`}
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={evaluated ? Math.round(bounded * 100) : undefined}
        aria-valuetext={percent(value)}
      >
        <div
          className={`h-full rounded-full transition-[width] duration-500 ${evaluated ? "bg-gradient-to-r from-indigo-500 to-violet-500" : "bg-slate-200"}`}
          style={{ width: evaluated ? `${bounded * 100}%` : "0%" }}
        />
      </div>
    </div>
  );
}

export function LoadingBlock({
  label = "正在加载学习进度…",
}: {
  label?: string;
}) {
  return (
    <div
      className="grid min-h-64 place-items-center rounded-3xl border border-slate-200 bg-white p-8 shadow-sm"
      role="status"
    >
      <div className="text-center">
        <span className="mx-auto block size-7 animate-spin rounded-full border-[3px] border-indigo-100 border-t-indigo-600" />
        <p className="mt-3 text-sm text-slate-500">{label}</p>
      </div>
    </div>
  );
}
