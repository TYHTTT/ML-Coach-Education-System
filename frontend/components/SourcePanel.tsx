import { BookIcon } from "@/components/Icons";
import { COURSE_META, type Source } from "@/lib/types";

interface SourcePanelProps {
  sources: Source[];
  retrievalCount?: number;
  compact?: boolean;
}

function location(source: Source): string {
  const values = [source.chapter, source.section]
    .map((value) => value?.trim())
    .filter(Boolean);
  if (source.page != null) values.push(`第 ${source.page} 页`);
  if (values.length === 0)
    values.push(
      Number.isFinite(source.chunk_index)
        ? `片段 ${source.chunk_index + 1}`
        : "来源位置未标注",
    );
  return values.join(" · ");
}

export default function SourcePanel({
  sources,
  retrievalCount,
  compact = false,
}: SourcePanelProps) {
  if (sources.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50/70 p-5 text-center">
        <BookIcon className="mx-auto size-6 text-slate-400" />
        <p className="mt-2 text-sm font-medium text-slate-600">
          本次回答暂无引用来源
        </p>
        <p className="mt-1 text-xs leading-5 text-slate-400">
          资料不足时 Tutor 会明确提示，不会生成虚假引用。
        </p>
      </div>
    );
  }

  return (
    <div className={compact ? "space-y-2" : "space-y-3"}>
      {!compact && (
        <div className="flex items-center justify-between px-1">
          <span className="text-xs text-slate-500">
            展示 {sources.length} 条来源
            {retrievalCount != null && retrievalCount !== sources.length
              ? ` · 召回 ${retrievalCount} 条`
              : ""}
          </span>
        </div>
      )}
      {sources.map((source, index) => (
        <article
          key={`${source.source_id}-${source.document_id}-${source.chunk_index}`}
          className={`rounded-2xl border border-slate-200 bg-white shadow-sm transition hover:border-indigo-200 ${
            compact ? "p-3" : "p-4"
          }`}
        >
          <div className="flex items-start gap-3">
            <span className="inline-flex h-7 min-w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-50 px-1.5 text-xs font-bold text-indigo-700">
              {source.source_id?.startsWith("authored:")
                ? "自编"
                : /^S\d+$/.test(source.source_id ?? "")
                  ? `[${source.source_id}]`
                  : `资料 ${index + 1}`}
            </span>
            <div className="min-w-0 flex-1">
              <p
                className="truncate text-sm font-semibold text-slate-800"
                title={source.source_file}
              >
                {source.source_file || source.title || "课程资料"}
              </p>
              {source.title && source.title !== source.source_file && (
                <p className="mt-0.5 truncate text-xs text-slate-500">
                  {source.title}
                </p>
              )}
            </div>
          </div>
          <p className="mt-2 text-xs text-slate-500">{location(source)}</p>
          {source.source_course && (
            <p className="mt-1 text-xs text-indigo-700">
              {COURSE_META[source.source_course]?.label ?? source.source_course}
              {source.topic_id ? ` · ${source.topic_id}` : ""}
            </p>
          )}
          <p
            className={`mt-2 text-xs leading-5 text-slate-600 ${compact ? "line-clamp-3" : "line-clamp-5"}`}
          >
            {source.snippet}
          </p>
          {typeof source.distance === "number" && (
            <div className="mt-3 flex items-center justify-between border-t border-slate-100 pt-2 text-[11px] text-slate-400">
              <span>检索距离</span>
              <span className="font-mono tabular-nums">
                {source.distance.toFixed(4)}
              </span>
            </div>
          )}
        </article>
      ))}
    </div>
  );
}
