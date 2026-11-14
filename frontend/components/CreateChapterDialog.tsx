"use client";

import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import {
  actionClass,
  fieldClass,
  primaryClass,
} from "@/components/KnowledgePointEditor";

export default function CreateChapterDialog({
  returnFocus,
  onSave,
  onCancel,
}: {
  returnFocus: HTMLElement;
  onSave: (title: string) => Promise<void>;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const heading = useId();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    const position = { left: scrollX, top: scrollY };
    const { overflow, paddingRight } = document.body.style;
    const scrollbar = innerWidth - document.documentElement.clientWidth;
    if (scrollbar > 0)
      document.body.style.paddingRight = `${parseFloat(getComputedStyle(document.body).paddingRight) + scrollbar}px`;
    document.body.style.overflow = "hidden";
    dialog.showModal();
    dialog.querySelector("input")?.focus({ preventScroll: true });
    return () => {
      dialog.close();
      document.body.style.overflow = overflow;
      document.body.style.paddingRight = paddingRight;
      window.scrollTo({ ...position, behavior: "instant" });
      requestAnimationFrame(() => {
        if (returnFocus.isConnected) returnFocus.focus({ preventScroll: true });
      });
    };
  }, [returnFocus]);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const title = String(
      new FormData(event.currentTarget).get("chapter_title"),
    ).trim();
    if (!title) {
      setError("请输入章节名称。");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await onSave(title);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "新增章节失败，请重试。",
      );
    } finally {
      setSaving(false);
    }
  }
  return (
    <dialog
      ref={ref}
      aria-labelledby={heading}
      onCancel={(event) => {
        event.preventDefault();
        if (!saving) onCancel();
      }}
      className="m-auto w-[calc(100%-2rem)] max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-xl backdrop:bg-slate-950/40"
    >
      <h2 id={heading} className="text-lg font-bold text-slate-900">
        新增章节
      </h2>
      <form onSubmit={submit} className="mt-5">
        <label className="block text-sm text-slate-700">
          章节名称
          <input
            name="chapter_title"
            required
            maxLength={100}
            disabled={saving}
            className={fieldClass}
          />
        </label>
        {error && (
          <p role="alert" className="mt-3 text-sm text-rose-700">
            {error}
          </p>
        )}
        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            disabled={saving}
            onClick={onCancel}
            className={actionClass}
          >
            取消
          </button>
          <button type="submit" disabled={saving} className={primaryClass}>
            {saving ? "正在创建…" : "创建章节"}
          </button>
        </div>
      </form>
    </dialog>
  );
}
