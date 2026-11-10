"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getAssessment } from "@/lib/api-content";
import type { Assessment } from "@/lib/types-content";
import {
  AlertIcon,
  ArrowRightIcon,
  CheckIcon,
  RefreshIcon,
  SparklesIcon,
  TargetIcon,
  TrophyIcon,
} from "@/components/Icons";
import MarkdownRenderer from "@/components/MarkdownRenderer";
import SourcePanel from "@/components/SourcePanel";
import { useStudent } from "@/components/StudentProvider";
import {
  ApiError,
  createPracticeSet,
  getPracticeSet,
  requestRemediation,
  submitPracticeSet,
} from "@/lib/api";
import { DIMENSION_LABELS, hasValidTopicEvidence, nextActionLabel, percent } from "@/lib/learning";
import type {
  CurriculumTopic,
  LearningMode,
  PracticeSubmitResult,
  PublicPracticeQuestion,
  PublicPracticeSet,
  RemediationResponse,
} from "@/lib/types";

const QUESTION_TYPE_LABELS: Record<string, string> = {
  concept_explanation: "概念解释",
  mathematical_reasoning: "数学推理",
  why_mechanism: "原理分析",
  code_reading: "代码阅读",
  case_analysis: "案例分析",
  multiple_choice: "选择题",
  numeric: "数值题",
  theorem_condition: "定理条件",
  calculation: "计算题",
  derivation: "推导题",
  proof_outline: "证明思路",
  error_correction: "纠错题",
  application: "应用题",
};

const DIFFICULTY_LABELS: Record<string, string> = {
  easy: "基础",
  medium: "中等",
  hard: "进阶",
};

const GATE_REQUIREMENT_LABELS: Record<string, string> = {
  mastery_threshold: "总体掌握度",
  valid_attempts: "有效练习次数",
  checkpoint_completed: "完成综合验收",
  checkpoint_score: "综合验收成绩",
  dimension_coverage: "能力维度覆盖",
  critical_misconceptions: "严重错误已解决",
  prerequisites_mastered: "前置知识点已掌握",
};

function isChoice(question: PublicPracticeQuestion): boolean {
  return question.question_type.toLowerCase().includes("choice") && Boolean(question.options?.length);
}

function isNumeric(question: PublicPracticeQuestion): boolean {
  return question.question_type.toLowerCase() === "numeric";
}

function diagnosisText(value: RemediationResponse["diagnosis"]): string {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map((item) => `- ${item}`).join("\n");
  return Object.entries(value).map(([key, item]) => `- **${key}**：${String(item)}`).join("\n");
}

function masteryValue(value: number | null): string {
  return value === null ? "尚未评估" : percent(value);
}

export default function PracticePanel({
  topic,
  onLearningUpdated,
  checkpointAllowed = true,
  initialAssessment = null,
  onActiveCheckpoint,
  checkpointBlockedReason,
}: {
  topic: CurriculumTopic;
  onLearningUpdated: () => void | Promise<void>;
  checkpointAllowed?: boolean;
  initialAssessment?: Assessment | null;
  onActiveCheckpoint?: (active: boolean) => void;
  checkpointBlockedReason?: string;
}) {
  const { withStudent, studentId } = useStudent();
  const [practiceSet, setPracticeSet] = useState<PublicPracticeSet | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [generatingMode, setGeneratingMode] = useState<LearningMode | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submissionId, setSubmissionId] = useState<string | null>(null);
  const [hadEvidenceBeforeSubmission, setHadEvidenceBeforeSubmission] = useState<boolean | null>(null);
  const [result, setResult] = useState<PracticeSubmitResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [remediation, setRemediation] = useState<RemediationResponse | null>(null);
  const [remediating, setRemediating] = useState(false);
  const practiceRef = useRef<HTMLDivElement | null>(null);
  const [assessmentPurpose, setAssessmentPurpose] = useState<string>("practice");
  const restoreKey = studentId ? `course-coach:assessment:${studentId}:${topic.id}` : null;

  const weakPoints = useMemo(() => {
    if (!result) return [];
    return Array.from(new Set(result.evaluations.flatMap((evaluation) => [
      ...evaluation.misconception_tags,
      ...evaluation.missing_points,
    ]))).slice(0, 6);
  }, [result]);
  const evaluationUncertain = result?.status === "evaluation_uncertain"
    || result?.evaluations.some((evaluation) => !evaluation.evaluation_reliable) === true;
  const attemptIdentifier = result
    ? [...result.evaluations].sort((left, right) => left.score - right.score).find((item) => item.attempt_id)?.attempt_id
      ?? result.attempt_id
      ?? result.submission_id
      ?? null
    : null;

  const installPracticeSet = useCallback((nextSet: PublicPracticeSet, shouldScroll = true) => {
    setPracticeSet(nextSet);
    setAnswers(Object.fromEntries(nextSet.questions.map((question) => [question.question_id, ""])));
    setResult((nextSet as Assessment).result ?? null);
    setSubmissionId(null);
    setHadEvidenceBeforeSubmission(null);
    setRemediation(null);
    setValidationError(null);
    setAssessmentPurpose((nextSet as Assessment).purpose === "prerequisite_test" ? "prerequisite_test" : nextSet.mode);
    if (shouldScroll) window.setTimeout(() => practiceRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  }, []);

  useEffect(() => {
    if (!restoreKey || initialAssessment) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      let saved: { id?: string; answers?: Record<string, string>; submissionId?: string } = {};
      try { saved = JSON.parse(window.localStorage.getItem(restoreKey) || "{}"); } catch { return; }
      if (!saved.id) return;
      void withStudent((id) => getAssessment(saved.id!, id)).then((assessment) => {
        if (cancelled) return;
        installPracticeSet(assessment, false);
        const allowedIds = new Set(assessment.questions.map((question) => question.question_id));
        setAnswers(Object.fromEntries(Object.entries(saved.answers ?? {}).filter(([id, answer]) => allowedIds.has(id) && typeof answer === "string")));
        setSubmissionId(saved.submissionId ?? null);
        setResult(assessment.result ?? null);
      }).catch((cause) => { if (!cancelled) setError(`无法恢复上次测试：${cause instanceof Error ? cause.message : "请检查连接"}。你可以重新加载页面，或开始一套新练习。`); });
    }, 0);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [restoreKey, initialAssessment, withStudent, installPracticeSet]);
  useEffect(() => {
    if (!initialAssessment) return;
    const timer = window.setTimeout(() => {
      installPracticeSet(initialAssessment);
      if (!restoreKey) return;
      try {
        const saved = JSON.parse(window.localStorage.getItem(restoreKey) || "{}");
        if (saved.id !== initialAssessment.practice_set_id) return;
        const allowed = new Set(initialAssessment.questions.map((question) => question.question_id));
        setAnswers(Object.fromEntries(Object.entries(saved.answers ?? {}).filter(([id, answer]) => allowed.has(id) && typeof answer === "string")) as Record<string, string>);
        setSubmissionId(typeof saved.submissionId === "string" ? saved.submissionId : null);
      } catch { /* The server instance remains available without local drafts. */ }
    }, 0);
    return () => window.clearTimeout(timer);
  }, [initialAssessment, installPracticeSet, restoreKey]);
  useEffect(() => {
    if (!restoreKey || !practiceSet) return;
    try { window.localStorage.setItem(restoreKey, JSON.stringify({ id: practiceSet.practice_set_id, answers, submissionId })); } catch { /* Server instance survives; only local answer drafts may be unavailable. */ }
  }, [restoreKey, practiceSet, answers, submissionId]);
  useEffect(() => { onActiveCheckpoint?.(Boolean(practiceSet && (practiceSet.mode === "checkpoint" || assessmentPurpose === "prerequisite_test") && !result)); }, [onActiveCheckpoint, practiceSet, result, assessmentPurpose]);

  async function generate(mode: LearningMode) {
    if (generatingMode || submitting || (mode === "checkpoint" && !checkpointAllowed)) return;
    setGeneratingMode(mode);
    setError(null);
    setValidationError(null);
    try {
      const nextSet = await withStudent((studentId) =>
        createPracticeSet(
          {
            topic_id: topic.id,
            mode,
            count: mode === "checkpoint" ? 5 : 3,
            difficulty: "adaptive",
          },
          studentId,
        ),
      );
      installPracticeSet(nextSet);
    } catch (cause) {
      if (cause instanceof ApiError && cause.code === "KNOWLEDGE_INSUFFICIENT") {
        setError(cause.message);
      } else {
        setError(cause instanceof Error ? cause.message : "练习生成失败，请稍后重试。");
      }
    } finally {
      setGeneratingMode(null);
    }
  }

  async function submit() {
    if (!practiceSet || submitting || result) return;
    const missing = practiceSet.questions.filter(
      (question) => question.required !== false && !answers[question.question_id]?.trim(),
    );
    if (missing.length > 0) {
      setValidationError(`请先完成所有必答题：第 ${missing.map((item) => item.position).join("、")} 题尚未作答。`);
      document.getElementById(`answer-${missing[0].question_id}`)?.focus();
      return;
    }

    setSubmitting(true);
    setError(null);
    setValidationError(null);
    const currentSubmissionId = submissionId ?? window.crypto.randomUUID();
    setSubmissionId(currentSubmissionId);
    if (hadEvidenceBeforeSubmission === null) {
      setHadEvidenceBeforeSubmission(hasValidTopicEvidence(topic));
    }
    try {
      const nextResult = await withStudent((studentId) =>
        submitPracticeSet(
          practiceSet.practice_set_id,
          {
            client_submission_id: currentSubmissionId,
            answers: practiceSet.questions.map((question) => ({
              question_id: question.question_id,
                  answer: (answers[question.question_id] ?? "").trim(),
            })),
          },
          studentId,
        ),
      );
      setResult(nextResult);
      await onLearningUpdated();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "答案提交失败。再次提交会复用同一提交编号，不会重复计分。");
    } finally {
      setSubmitting(false);
    }
  }

  async function loadTargetedSet(practiceSetId: string) {
    setGeneratingMode("practice");
    setError(null);
    try {
      const nextSet = await withStudent((studentId) => getPracticeSet(practiceSetId, studentId));
      installPracticeSet(nextSet);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "专项练习加载失败。");
    } finally {
      setGeneratingMode(null);
    }
  }

  async function remediate() {
    if (!attemptIdentifier || remediating) return;
    setRemediating(true);
    setError(null);
    try {
      const response = await withStudent((studentId) =>
        requestRemediation({ topic_id: topic.id, attempt_id: attemptIdentifier }, studentId),
      );
      setRemediation(response);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "补救内容生成失败，请稍后重试。");
    } finally {
      setRemediating(false);
    }
  }

  return (
    <section id="practice" className="scroll-mt-24 space-y-5">
      <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-soft sm:p-6">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
          <div className="max-w-xl">
            <div className="flex items-center gap-2 text-xs font-semibold text-indigo-600"><TargetIcon className="size-4" />主动检验理解</div>
            <h2 className="mt-2 text-lg font-bold text-slate-900">AI 按课程资料动态出题</h2>
            <p className="mt-2 text-sm leading-6 text-slate-500">由 AI 根据当前知识点的课程资料和薄弱维度生成新题。普通练习 3 题，综合验收 5 题；提交后显示评价，刷新可继续原题。资料不足时会明确提示。</p>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <button
              type="button"
              onClick={() => void generate("practice")}
              disabled={Boolean(generatingMode) || submitting}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-45"
            >
              {generatingMode === "practice" ? <RefreshIcon className="size-4 animate-spin" /> : <SparklesIcon className="size-4" />}
              AI 生成 3 道练习
            </button>
            <button
              type="button"
              onClick={() => void generate("checkpoint")}
              disabled={Boolean(generatingMode) || submitting || !checkpointAllowed}
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm font-semibold text-slate-700 transition hover:border-cyan-300 hover:bg-cyan-50 hover:text-cyan-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500 disabled:cursor-not-allowed disabled:opacity-45"
            >
              {generatingMode === "checkpoint" ? <RefreshIcon className="size-4 animate-spin" /> : <TrophyIcon className="size-4" />}
              AI 生成 5 道综合验收
            </button>
          </div>
        </div>
        {!checkpointAllowed && <p className="mt-4 rounded-xl bg-amber-50 px-3 py-2 text-xs leading-6 text-amber-800">{checkpointBlockedReason || "正式测试前需满足前置能力与学习证据要求。可以先完成无提示练习，并查看知识点页的下一步建议。"}</p>}
      </div>

      {error && (
        <div className="flex items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800" role="alert">
          <AlertIcon className="mt-0.5 size-4 shrink-0" />
          <span className="flex-1">{error}</span>
          <button type="button" onClick={() => setError(null)} className="text-xs font-semibold">关闭</button>
        </div>
      )}

      {practiceSet && (
        <div ref={practiceRef} className="scroll-mt-24 space-y-4">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.16em] text-indigo-600">{practiceSet.mode === "checkpoint" ? "Checkpoint" : "Practice"}</p>
              <h2 className="mt-1 text-xl font-bold text-slate-900">{assessmentPurpose === "prerequisite_test" ? "前置能力小测" : practiceSet.mode === "checkpoint" ? "知识点综合验收" : "主动练习"}</h2>
            </div>
            <p className="text-xs text-slate-400">共 {practiceSet.questions.length} 题 · 所有题目均需作答</p>
          </div>

          {practiceSet.questions.map((question) => {
            const evaluation = result?.evaluations.find((item) => item.question_id === question.question_id);
            return (
              <article key={question.question_id} className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
                <div className="border-b border-slate-100 p-5 sm:p-6">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="grid size-7 place-items-center rounded-lg bg-slate-900 text-xs font-bold text-white">{question.position}</span>
                    <span className="rounded-full bg-indigo-50 px-2.5 py-1 text-[10px] font-semibold text-indigo-700">{QUESTION_TYPE_LABELS[question.question_type] ?? question.question_type}</span>
                    <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-semibold text-slate-600">{DIFFICULTY_LABELS[question.difficulty] ?? question.difficulty}</span>
                    {question.dimension_names.map((dimension) => (
                      <span key={dimension} className="rounded-full border border-slate-200 px-2.5 py-1 text-[10px] text-slate-500">{DIMENSION_LABELS[dimension] ?? dimension}</span>
                    ))}
                  </div>
                  <div className="mt-4"><MarkdownRenderer content={question.question} /></div>
                </div>

                <div className="p-5 sm:p-6">
                  {isChoice(question) ? (
                    <fieldset disabled={submitting || Boolean(result)}>
                      <legend className="text-xs font-semibold text-slate-600">选择一个答案 <span className="text-rose-500">*</span></legend>
                      <div className="mt-3 grid gap-2">
                        {question.options?.map((option, optionIndex) => (
                          <label key={option.value} className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3 text-sm transition ${answers[question.question_id] === option.value ? "border-indigo-300 bg-indigo-50 text-indigo-900" : "border-slate-200 hover:bg-slate-50"}`}>
                            <input
                              id={optionIndex === 0 ? `answer-${question.question_id}` : `answer-${question.question_id}-${optionIndex}`}
                              type="radio"
                              name={`answer-${question.question_id}`}
                              value={option.value}
                              checked={answers[question.question_id] === option.value}
                              onChange={(event) => setAnswers((current) => ({ ...current, [question.question_id]: event.target.value }))}
                              className="mt-0.5 size-4 accent-indigo-600"
                            />
                            <span className="leading-6"><span className="mr-2 font-semibold text-slate-500">{option.value}</span>{option.label}</span>
                          </label>
                        ))}
                      </div>
                    </fieldset>
                  ) : isNumeric(question) ? (
                    <div>
                      <label htmlFor={`answer-${question.question_id}`} className="text-xs font-semibold text-slate-600">数值答案 <span className="text-rose-500">*</span></label>
                      <input
                        id={`answer-${question.question_id}`}
                        type="text"
                        inputMode="decimal"
                        value={answers[question.question_id] ?? ""}
                        onChange={(event) => setAnswers((current) => ({ ...current, [question.question_id]: event.target.value }))}
                        disabled={submitting || Boolean(result)}
                        placeholder="输入数值；如有单位请一并填写"
                        className="mt-2 h-11 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm outline-none transition focus:border-indigo-300 focus:bg-white focus:ring-4 focus:ring-indigo-100/60 disabled:opacity-70"
                      />
                    </div>
                  ) : (
                    <div>
                      <label htmlFor={`answer-${question.question_id}`} className="text-xs font-semibold text-slate-600">你的回答 <span className="text-rose-500">*</span></label>
                      <textarea
                        id={`answer-${question.question_id}`}
                        rows={5}
                        value={answers[question.question_id] ?? ""}
                        onChange={(event) => setAnswers((current) => ({ ...current, [question.question_id]: event.target.value }))}
                        disabled={submitting || Boolean(result)}
                        placeholder="写出关键步骤和理由；代码阅读题写预期输出或解释"
                        className="mt-2 min-h-32 w-full resize-y rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 text-sm leading-6 outline-none transition focus:border-indigo-300 focus:bg-white focus:ring-4 focus:ring-indigo-100/60 disabled:opacity-70"
                      />
                    </div>
                  )}


                  {evaluation && (
                    <div className={`mt-5 rounded-2xl border p-4 ${evaluation.score >= 80 ? "border-emerald-200 bg-emerald-50" : evaluation.score >= 60 ? "border-amber-200 bg-amber-50" : "border-rose-200 bg-rose-50"}`}>
                      <div className="flex items-center justify-between gap-4">
                        <span className="text-sm font-bold text-slate-900">本题评价 · {evaluation.verdict}</span>
                        <span className="text-lg font-bold tabular-nums text-slate-900">{Math.round(evaluation.score)} 分</span>
                      </div>
                      <p className="mt-3 text-sm leading-6 text-slate-700">{evaluation.feedback}</p>
                      {evaluation.correct_points.length > 0 && (
                        <div className="mt-3"><p className="text-xs font-semibold text-emerald-800">答对的要点</p><ul className="mt-1 list-disc space-y-1 pl-5 text-xs leading-5 text-slate-600">{evaluation.correct_points.map((point) => <li key={point}>{point}</li>)}</ul></div>
                      )}
                      {evaluation.missing_points.length > 0 && (
                        <div className="mt-3"><p className="text-xs font-semibold text-amber-800">需要补充</p><ul className="mt-1 list-disc space-y-1 pl-5 text-xs leading-5 text-slate-600">{evaluation.missing_points.map((point) => <li key={point}>{point}</li>)}</ul></div>
                      )}
                      {evaluation.reference_answer && (
                        <details className="mt-3 border-t border-black/5 pt-3">
                          <summary className="cursor-pointer text-xs font-semibold text-indigo-700">提交后参考答案</summary>
                          <div className="mt-2"><MarkdownRenderer content={evaluation.reference_answer} /></div>
                        </details>
                      )}
                      {evaluation.sources.length > 0 && (
                        <details className="mt-3 border-t border-black/5 pt-3">
                          <summary className="cursor-pointer text-xs font-semibold text-indigo-700">评价依据来源</summary>
                          <div className="mt-3"><SourcePanel sources={evaluation.sources} /></div>
                        </details>
                      )}
                    </div>
                  )}
                </div>
              </article>
            );
          })}

          {!result && (
            <div className="sticky bottom-3 z-10 rounded-2xl border border-slate-200 bg-white/95 p-4 shadow-xl backdrop-blur">
              {validationError && <p className="mb-3 text-sm font-medium text-rose-700" role="alert">{validationError}</p>}
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-xs leading-5 text-slate-500">提交后将按照本题评分规则评价，并更新学习证据。提交中请勿重复点击。</p>
                <button
                  type="button"
                  onClick={() => void submit()}
                  disabled={submitting}
                  className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-500 focus-visible:ring-offset-2 disabled:cursor-wait disabled:opacity-60"
                >
                  {submitting ? <RefreshIcon className="size-4 animate-spin" /> : <CheckIcon className="size-4" />}
                  {submitting ? "正在评价，请稍候…" : "提交整套答案"}
                </button>
              </div>
            </div>
          )}

          {practiceSet.source_summary.length > 0 && (
            <details className="rounded-2xl border border-slate-200 bg-white p-4">
              <summary className="cursor-pointer text-xs font-semibold text-slate-600">本套题的资料来源</summary>
              <ul className="mt-3 space-y-2 text-xs text-slate-500">
                {practiceSet.source_summary.map((source) => <li key={source.source_id} className="break-words">{source.title || source.source_file}<span className="ml-2 text-slate-400">{source.source_file}</span></li>)}
              </ul>
            </details>
          )}
        </div>
      )}

      {result && (
        <section className="overflow-hidden rounded-3xl border border-indigo-200 bg-white shadow-soft" aria-label="学习结果">
          <div className="bg-gradient-to-r from-indigo-600 to-violet-700 p-5 text-white sm:p-6">
            <div className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className="text-xs font-semibold text-indigo-100">{assessmentPurpose === "prerequisite_test" ? "前置能力小测结果 · 仅验证对应局部技能" : `学习结果 · ${topic.title}`}</p>
                <p className="mt-2 text-4xl font-bold tabular-nums">{Math.round(result.total_score)}<span className="ml-1 text-lg font-medium text-indigo-200">/ 100</span></p>
              </div>
              {assessmentPurpose !== "prerequisite_test" && <div className="rounded-2xl bg-white/10 px-4 py-3 backdrop-blur">
                <p className="text-[11px] text-indigo-100">掌握度变化</p>
                <p className="mt-1 text-lg font-bold tabular-nums">
                  {masteryValue(hadEvidenceBeforeSubmission === false ? null : result.mastery_before)}
                  <span className="mx-1 text-indigo-200">→</span>
                  {masteryValue(evaluationUncertain && hadEvidenceBeforeSubmission === false ? null : result.mastery_after)}
                </p>
              </div>}
            </div>
          </div>
          {assessmentPurpose === "prerequisite_test" && <p className="border-b border-indigo-100 bg-indigo-50 px-5 py-4 text-sm leading-6 text-indigo-900">本次仅记录已验证的前置能力，不将整门数学课程标记为已掌握。可以回到上方前置卡查看最新缺口，再完成当前知识点练习。</p>}
          {evaluationUncertain && (
            <div className="flex items-start gap-3 border-b border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-900 sm:px-6" role="alert">
              <AlertIcon className="mt-0.5 size-4 shrink-0" />
              <div>
                <p className="font-semibold">本次评价置信度不足，未计入掌握度</p>
                <p className="mt-1 text-xs leading-5 text-amber-800">你可以保留答案重新请求评价，或生成一套新练习。系统不会把不可靠评价当成学习证据。</p>
              </div>
            </div>
          )}
          <div className="grid gap-6 p-5 sm:p-6 lg:grid-cols-2">
            <div>
              <h3 className="text-sm font-bold text-slate-900">主要薄弱点</h3>
              {weakPoints.length > 0 ? (
                <ul className="mt-3 space-y-2">{weakPoints.map((point) => <li key={point} className="flex gap-2 rounded-xl bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-900"><AlertIcon className="mt-0.5 size-3.5 shrink-0" />{point}</li>)}</ul>
              ) : <p className="mt-3 text-sm text-emerald-700">没有识别到明显薄弱点，继续保持。</p>}
            </div>
            {assessmentPurpose === "prerequisite_test" ? <div><h3 className="text-sm font-bold text-slate-900">局部前置能力验证</h3><p className="mt-3 text-sm leading-7 text-slate-600">系统按本次题目覆盖的能力与可靠评分保存验证证据。是否已满足当前知识点的要求，请查看更新后的前置卡；未覆盖的能力仍需补学。</p><a href="#prerequisites" className="mt-4 inline-block text-sm font-semibold text-indigo-700">查看最新前置缺口 ↑</a></div> : <div>
              <h3 className="text-sm font-bold text-slate-900">Mastery Gate</h3>
              <div className={`mt-3 rounded-2xl border p-4 ${result.gate.passed ? "border-emerald-200 bg-emerald-50" : "border-slate-200 bg-slate-50"}`}>
                <p className="flex items-center gap-2 text-sm font-bold text-slate-900">
                  {result.gate.passed ? <CheckIcon className="size-4 text-emerald-600" /> : <TargetIcon className="size-4 text-indigo-600" />}
                  {result.gate.passed ? "已通过，可以进入下一知识点" : "尚未通过，继续积累学习证据"}
                </p>
                <p className="mt-2 text-sm text-slate-600">下一步：{nextActionLabel(result.gate.next_action ?? result.next_action)}</p>
                {Object.keys(result.gate.requirements).length > 0 && (
                  <details className="mt-3">
                    <summary className="cursor-pointer text-xs font-semibold text-slate-500">查看 Gate 条件</summary>
                    <ul className="mt-2 space-y-2 text-xs text-slate-500">
                      {Object.entries(result.gate.requirements).map(([key, value]) => {
                        const detail = value && typeof value === "object" ? value as Record<string, unknown> : null;
                        const passed = detail && typeof detail.passed === "boolean" ? detail.passed : Boolean(value);
                        const current = detail?.current;
                        const required = detail?.required;
                        return (
                          <li key={key} className="flex items-start gap-2">
                            <span className={`mt-0.5 font-bold ${passed ? "text-emerald-600" : "text-amber-600"}`} aria-hidden="true">{passed ? "✓" : "○"}</span>
                            <span>
                              <span className="font-medium text-slate-700">{GATE_REQUIREMENT_LABELS[key] ?? key.replaceAll("_", " ")}</span>
                              {current !== undefined && required !== undefined && <span> · 当前 {String(current)} / 要求 {String(required)}</span>}
                            </span>
                          </li>
                        );
                      })}
                    </ul>
                  </details>
                )}
              </div>
            </div>}
          </div>
          <div className="flex flex-col gap-3 border-t border-slate-100 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
            <p className="text-sm font-semibold text-slate-800">下一步：{assessmentPurpose === "prerequisite_test" ? "查看前置卡，继续补学或练习当前知识点" : nextActionLabel(result.gate.next_action ?? result.next_action)}</p>
            <div className="flex flex-col gap-2 sm:flex-row">
              {evaluationUncertain && (
                <button
                  type="button"
                  onClick={() => {
                    setResult(null);
                    setSubmissionId(null);
                    setError(null);
                  }}
                  className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
                >
                  <RefreshIcon className="size-4" /> 保留答案，重新评价
                </button>
              )}
              {attemptIdentifier && !result.gate.passed && !evaluationUncertain && assessmentPurpose !== "prerequisite_test" && (
                <button type="button" onClick={() => void remediate()} disabled={remediating} className="inline-flex items-center justify-center gap-2 rounded-xl border border-amber-300 bg-amber-50 px-4 py-2.5 text-sm font-semibold text-amber-800 transition hover:bg-amber-100 disabled:cursor-wait disabled:opacity-60">
                  {remediating ? <RefreshIcon className="size-4 animate-spin" /> : <SparklesIcon className="size-4" />}
                  生成针对性补救
                </button>
              )}
              <button type="button" onClick={() => void generate("practice")} disabled={Boolean(generatingMode)} className="inline-flex items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-60">
                再练一组 <ArrowRightIcon className="size-4" />
              </button>
            </div>
          </div>
        </section>
      )}

      {remediation && (
        <section id="remediation" className="scroll-mt-24 rounded-3xl border border-amber-200 bg-amber-50/70 p-5 shadow-sm sm:p-6">
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-amber-700">Targeted Remediation</p>
          <h2 className="mt-2 text-xl font-bold text-slate-900">针对性补救</h2>
          <div className="mt-5 grid gap-4 lg:grid-cols-2">
            <div className="rounded-2xl bg-white p-4"><h3 className="text-xs font-bold text-rose-700">错误诊断</h3><div className="mt-2"><MarkdownRenderer content={diagnosisText(remediation.diagnosis)} /></div></div>
            <div className="rounded-2xl bg-white p-4"><h3 className="text-xs font-bold text-emerald-700">正确理解</h3><div className="mt-2"><MarkdownRenderer content={remediation.explanation} /></div></div>
          </div>
          {remediation.contrast_example && <div className="mt-4 rounded-2xl border border-amber-200 bg-white p-4"><h3 className="text-xs font-bold text-amber-800">对比例子</h3><div className="mt-2"><MarkdownRenderer content={remediation.contrast_example} /></div></div>}
          <div className="mt-5 flex flex-wrap gap-3">
            {remediation.targeted_question_set_id && <button type="button" onClick={() => void loadTargetedSet(remediation.targeted_question_set_id!)} className="inline-flex items-center gap-2 rounded-xl bg-amber-700 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-amber-800">开始专项小题 <ArrowRightIcon className="size-4" /></button>}
            {remediation.sources.length > 0 && <details className="w-full rounded-xl border border-amber-200 bg-white p-3"><summary className="cursor-pointer text-xs font-semibold text-amber-800">查看补救资料来源</summary><div className="mt-3"><SourcePanel sources={remediation.sources} /></div></details>}
          </div>
        </section>
      )}
    </section>
  );
}
