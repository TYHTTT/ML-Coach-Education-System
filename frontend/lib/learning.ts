import type {
  CurriculumTopicSummary,
  DimensionProgress,
  NextAction,
  TopicStatus,
} from "@/lib/types";

export const TOPIC_STATUS_META: Record<
  TopicStatus,
  { label: string; symbol: string; badge: string; border: string }
> = {
  not_started: {
    label: "未开始",
    symbol: "○",
    badge: "border-sky-200 bg-sky-50 text-sky-700",
    border: "border-sky-200",
  },
  learning: {
    label: "学习中",
    symbol: "▶",
    badge: "border-indigo-200 bg-indigo-50 text-indigo-700",
    border: "border-indigo-200",
  },
  practicing: {
    label: "待练习",
    symbol: "✎",
    badge: "border-violet-200 bg-violet-50 text-violet-700",
    border: "border-violet-200",
  },
  needs_remediation: {
    label: "需要补救",
    symbol: "!",
    badge: "border-amber-200 bg-amber-50 text-amber-800",
    border: "border-amber-200",
  },
  ready_for_checkpoint: {
    label: "待测试",
    symbol: "◆",
    badge: "border-cyan-200 bg-cyan-50 text-cyan-800",
    border: "border-cyan-200",
  },
  mastered: {
    label: "已通过",
    symbol: "✓",
    badge: "border-emerald-200 bg-emerald-50 text-emerald-700",
    border: "border-emerald-200",
  },
};

export const NEXT_ACTION_LABELS: Record<string, string> = {
  start_learning: "开始知识点学习",
  teach: "查看针对性讲解",
  practice: "继续主动练习",
  remediate: "进行薄弱点补救",
  take_checkpoint: "完成知识点综合验收",
  continue_to_next_topic: "进入下一个知识点",
  course_completed: "课程学习已完成",
};

export function nextActionLabel(action?: NextAction | null): string {
  if (!action) return "继续学习";
  return NEXT_ACTION_LABELS[action] ?? action.replaceAll("_", " ");
}

export function statusMeta(status?: TopicStatus | string | null) {
  return (
    TOPIC_STATUS_META[(status ?? "not_started") as TopicStatus] ??
    TOPIC_STATUS_META.not_started
  );
}

export function percent(value?: number | null): string {
  if (value === null || value === undefined || !Number.isFinite(value))
    return "尚未评估";
  return `${Math.round(Math.min(1, Math.max(0, value)) * 100)}%`;
}

export function scoreLabel(value?: number | null): string {
  if (value === null || value === undefined || !Number.isFinite(value))
    return "—";
  return `${Math.round(value)} 分`;
}

/** Keep the uninformative Beta(1,1) prior out of student-facing progress. */
export function hasValidTopicEvidence(
  topic: Pick<
    CurriculumTopicSummary,
    "status" | "mastery" | "mastery_display" | "confidence" | "evidence_count"
  > & { dimensions?: DimensionProgress[] },
): boolean {
  if (topic.status === "not_started") return false;
  if (typeof topic.evidence_count === "number") return topic.evidence_count > 0;
  if (topic.mastery_display?.trim() === "尚未评估") return false;

  const dimensionEvidence = topic.dimensions?.some(
    (dimension) =>
      typeof dimension.evidence_count === "number" &&
      dimension.evidence_count > 0,
  );
  if (dimensionEvidence) return true;

  if (
    (topic.confidence === null ||
      topic.confidence === undefined ||
      topic.confidence <= 0) &&
    (topic.mastery === null || Math.abs(topic.mastery - 0.5) < 1e-9)
  ) {
    return false;
  }
  return topic.mastery !== null && topic.mastery !== undefined;
}
