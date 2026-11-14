"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useAdmin } from "@/components/AdminProvider";
import KnowledgePointEditor, {
  actionClass,
  fieldClass,
  primaryClass,
} from "@/components/KnowledgePointEditor";
import DeleteChapterDialog from "@/components/DeleteChapterDialog";
import CreateChapterDialog from "@/components/CreateChapterDialog";
import { ArrowRightIcon } from "@/components/Icons";
import {
  manageTopics,
  type ManagedOutline,
  type ManagedTopic,
  type TopicGroup,
  type TopicValues,
} from "@/lib/topic-management";

const message = (error: unknown) =>
  error instanceof Error ? error.message : "操作失败，请重试。";
export default function CourseTopicsManager({
  courseId,
  onInteractionChange,
}: {
  courseId: string;
  onInteractionChange?: (busy: boolean) => void;
}) {
  const { withAdmin } = useAdmin();
  const [outline, setOutline] = useState<ManagedOutline | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [version, setVersion] = useState(0);
  const [busy, setBusy] = useState(false);
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(
    () => new Set(),
  );
  const chapterIdPrefix = useId();
  const [editor, setEditor] = useState<{
    topic: ManagedTopic | null;
    initialGroupId?: string;
    returnFocus: HTMLButtonElement;
  } | null>(null);
  const [removing, setRemoving] = useState<ManagedTopic | null>(null);
  const [renaming, setRenaming] = useState<TopicGroup | null>(null);
  const [removingGroup, setRemovingGroup] = useState<{
    group: TopicGroup;
    topics: ManagedTopic[];
    returnFocus: HTMLButtonElement;
  } | null>(null);
  const [creatingGroup, setCreatingGroup] = useState<{
    returnFocus: HTMLButtonElement;
  } | null>(null);
  const renamePanel = useRef<HTMLFormElement>(null);
  const removePanel = useRef<HTMLElement>(null);
  useEffect(() => {
    if (renaming) {
      renamePanel.current?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
      renamePanel.current
        ?.querySelector("input")
        ?.focus({ preventScroll: true });
    }
  }, [renaming]);
  useEffect(() => {
    if (removing) {
      removePanel.current?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
      removePanel.current?.focus({ preventScroll: true });
    }
  }, [removing]);
  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setError("");
      try {
        const data = await withAdmin((token) =>
          manageTopics(
            token,
            courseId,
            "GET",
            "",
            undefined,
            controller.signal,
          ),
        );
        if (!controller.signal.aborted) {
          setOutline(data);
          setCollapsedGroups(
            (current) =>
              new Set(
                data.groups
                  .filter((group) => current.has(group.id))
                  .map((group) => group.id),
              ),
          );
        }
      } catch (cause) {
        if (!controller.signal.aborted) setError(message(cause));
      }
    }, 0);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [courseId, version, withAdmin]);
  async function mutate(
    method: string,
    suffix: string,
    body?: unknown,
    reorderedGroups?: string[],
  ) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const data = await withAdmin((token) =>
        manageTopics(token, courseId, method, suffix, body),
      );
      // Reordering renumbers stage IDs; keep the fold state with the chapter.
      setCollapsedGroups(
        (current) =>
          new Set(
            data.groups
              .filter((group) =>
                current.has(
                  group.stage !== null
                    ? (reorderedGroups?.[group.stage - 1] ?? group.id)
                    : group.id,
                ),
              )
              .map((group) => group.id),
          ),
      );
      setOutline(data);
      setNotice("编排已保存，学生端目录已同步。");
      return data;
    } finally {
      setBusy(false);
    }
  }
  async function act(action: () => Promise<unknown>) {
    try {
      await action();
    } catch (cause) {
      setError(message(cause));
    }
  }
  async function save(values: TopicValues) {
    if (!editor) return;
    const suffix = editor.topic ? `/${editor.topic.id}` : "";
    await mutate(editor.topic ? "PUT" : "POST", suffix, values);
    setEditor(null);
  }
  function moveTopic(group: TopicGroup, index: number, offset: number) {
    const ids = group.topics.map((t) => t.id);
    [ids[index], ids[index + offset]] = [ids[index + offset], ids[index]];
    void act(() =>
      mutate("PUT", "/order", { group_id: group.id, topic_ids: ids }),
    );
  }
  function moveGroup(group: TopicGroup, offset: number) {
    const ids = outline!.groups
      .filter((g) => g.stage !== null)
      .map((g) => g.id);
    const index = ids.indexOf(group.id);
    [ids[index], ids[index + offset]] = [ids[index + offset], ids[index]];
    void act(() => mutate("POST", "/groups/order", { group_ids: ids }, ids));
  }
  function toggleGroup(id: string) {
    setCollapsedGroups((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }
  const interactionBusy =
    busy ||
    Boolean(editor) ||
    Boolean(removing) ||
    Boolean(renaming) ||
    Boolean(removingGroup) ||
    Boolean(creatingGroup);
  useEffect(() => {
    onInteractionChange?.(interactionBusy);
  }, [interactionBusy, onInteractionChange]);
  const chapters = outline?.groups.filter((g) => g.stage !== null) ?? [];
  return (
    <section aria-label="章节编排" className="mt-8">
      <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900">章节编排</h2>
          <p className="mt-2 text-sm text-slate-500">
            管理章节和学习顺序，讲解内容由 Dify Agent 提供。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={
              interactionBusy ||
              !outline?.groups.some((group) => collapsedGroups.has(group.id))
            }
            className={actionClass}
            onClick={() => setCollapsedGroups(new Set())}
          >
            展开全部
          </button>
          <button
            type="button"
            disabled={
              interactionBusy ||
              !outline?.groups.some((group) => !collapsedGroups.has(group.id))
            }
            className={actionClass}
            onClick={() =>
              setCollapsedGroups(
                new Set(outline?.groups.map((group) => group.id)),
              )
            }
          >
            收起全部
          </button>
          <button
            disabled={!outline || interactionBusy}
            className={primaryClass}
            onClick={(event) =>
              setCreatingGroup({ returnFocus: event.currentTarget })
            }
          >
            新增章节
          </button>
        </div>
      </div>
      {error && (
        <div
          role="alert"
          className="mt-5 flex justify-between gap-4 rounded-xl bg-rose-50 p-3 text-sm text-rose-700"
        >
          <p>{error}</p>
          <button
            disabled={busy}
            onClick={() => {
              setOutline(null);
              setVersion((v) => v + 1);
            }}
            className="shrink-0 underline"
          >
            刷新目录
          </button>
        </div>
      )}
      {notice && (
        <p role="status" className="mt-4 text-sm text-emerald-700">
          {notice}
        </p>
      )}
      {creatingGroup && (
        <CreateChapterDialog
          {...creatingGroup}
          onCancel={() => setCreatingGroup(null)}
          onSave={async (title) => {
            const data = await mutate("POST", "/groups", { title });
            const added = data.groups.find(
              (group) => !outline?.groups.some((old) => old.id === group.id),
            );
            setCreatingGroup(null);
            if (added)
              requestAnimationFrame(() =>
                document
                  .getElementById(`${chapterIdPrefix}-${added.id}`)
                  ?.closest("section")
                  ?.scrollIntoView({ behavior: "smooth", block: "center" }),
              );
          }}
        />
      )}
      {editor && outline && (
        <KnowledgePointEditor
          key={editor.topic?.id ?? "new"}
          {...editor}
          courseId={courseId}
          groups={outline.groups}
          onSave={save}
          onCancel={() => setEditor(null)}
        />
      )}
      {removingGroup && (
        <DeleteChapterDialog
          {...removingGroup}
          onCancel={() => setRemovingGroup(null)}
          onReload={() => {
            setRemovingGroup(null);
            setVersion((value) => value + 1);
          }}
          onDelete={async () => {
            await mutate("DELETE", `/groups/${removingGroup.group.stage}`, {
              title: removingGroup.group.title,
              topic_ids: removingGroup.topics.map((topic) => topic.id),
            });
            setRemovingGroup(null);
          }}
        />
      )}
      {renaming && (
        <form
          ref={renamePanel}
          aria-label="重命名章节"
          className="mt-5 flex flex-wrap items-end gap-3 rounded-xl border border-indigo-200 bg-white p-4"
          onSubmit={(e) => {
            e.preventDefault();
            const title = String(
              new FormData(e.currentTarget).get("chapter_title"),
            ).trim();
            void act(async () => {
              await mutate("PATCH", `/groups/${renaming.stage}`, { title });
              setRenaming(null);
            });
          }}
        >
          <label className="flex-1 text-sm text-slate-600">
            章节名称
            <input
              name="chapter_title"
              required
              maxLength={100}
              defaultValue={renaming.title}
              className={fieldClass}
            />
          </label>
          <button disabled={busy} className={primaryClass}>
            保存名称
          </button>
          <button
            disabled={busy}
            type="button"
            className={actionClass}
            onClick={() => setRenaming(null)}
          >
            取消
          </button>
        </form>
      )}
      {removing && (
        <section
          ref={removePanel}
          tabIndex={-1}
          aria-label="确认删除知识点"
          className="mt-5 rounded-xl border border-rose-200 bg-white p-4"
        >
          <p className="text-sm text-slate-700">
            确定永久删除知识点“{removing.title}
            ”？关联关系、学习状态、历史练习和相关会话记录将一并删除，无法恢复。
          </p>
          <div className="mt-3 flex gap-3">
            <button
              disabled={busy}
              className="rounded-xl bg-rose-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
              onClick={() =>
                void act(async () => {
                  await mutate("DELETE", `/${removing.id}`);
                  setRemoving(null);
                })
              }
            >
              确认永久删除
            </button>
            <button
              disabled={busy}
              className={actionClass}
              onClick={() => setRemoving(null)}
            >
              取消
            </button>
          </div>
        </section>
      )}
      {!outline && !error && (
        <p role="status" className="py-10 text-slate-500">
          正在加载知识点…
        </p>
      )}
      {outline && !outline.groups.length && (
        <div className="mt-8 rounded-2xl border border-dashed border-slate-300 p-10 text-center text-sm text-slate-500">
          暂无章节，点击“新增章节”创建第一个章节。
        </div>
      )}
      <div className="mt-6 space-y-5">
        {outline?.groups.map((group) => (
          <section
            key={group.id}
            className="overflow-hidden rounded-2xl border border-slate-200 bg-white"
            aria-label={group.title}
          >
            <div className="flex flex-wrap items-center justify-between gap-3 bg-slate-50 px-5 py-4">
              <h2 className="min-w-0 flex-1 basis-full font-semibold text-slate-800 sm:basis-auto">
                <button
                  type="button"
                  disabled={interactionBusy}
                  aria-label={`${collapsedGroups.has(group.id) ? "展开" : "收起"}章节${group.title}`}
                  aria-expanded={!collapsedGroups.has(group.id)}
                  aria-controls={`${chapterIdPrefix}-${group.id}`}
                  onClick={() => toggleGroup(group.id)}
                  className="-my-2 flex w-full items-center gap-2 rounded-lg py-2 text-left hover:text-indigo-700 disabled:opacity-50"
                >
                  <ArrowRightIcon
                    className={`size-4 shrink-0 text-slate-400 transition-transform ${collapsedGroups.has(group.id) ? "" : "rotate-90"}`}
                  />
                  <span className="break-words">{group.title}</span>
                  <span className="shrink-0 text-xs font-normal text-slate-400">
                    {group.topics.length} 个知识点
                  </span>
                </button>
              </h2>
              {group.stage !== null && (
                <div className="flex flex-wrap gap-2">
                  <button
                    disabled={interactionBusy || group.id === chapters[0]?.id}
                    aria-label={`上移章节${group.title}`}
                    className={actionClass}
                    onClick={() => moveGroup(group, -1)}
                  >
                    ↑
                  </button>
                  <button
                    disabled={
                      interactionBusy || group.id === chapters.at(-1)?.id
                    }
                    aria-label={`下移章节${group.title}`}
                    className={actionClass}
                    onClick={() => moveGroup(group, 1)}
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    disabled={interactionBusy}
                    aria-label={`在${group.title}中新增知识点`}
                    className={primaryClass}
                    onClick={(event) => {
                      setCollapsedGroups((current) => {
                        const next = new Set(current);
                        next.delete(group.id);
                        return next;
                      });
                      setEditor({
                        topic: null,
                        initialGroupId: group.id,
                        returnFocus: event.currentTarget,
                      });
                    }}
                  >
                    新增知识点
                  </button>
                  <button
                    disabled={interactionBusy}
                    className={actionClass}
                    onClick={() => setRenaming(group)}
                  >
                    重命名章节
                  </button>
                  <button
                    disabled={interactionBusy}
                    aria-label={`删除章节${group.title}`}
                    className={`${actionClass} text-rose-700`}
                    onClick={(event) =>
                      setRemovingGroup({
                        group,
                        topics: [
                          ...group.topics,
                          ...outline!.removed_topics.filter(
                            (topic) => topic.parent_group_id === group.id,
                          ),
                        ],
                        returnFocus: event.currentTarget,
                      })
                    }
                  >
                    删除章节
                  </button>
                </div>
              )}
            </div>
            <div
              id={`${chapterIdPrefix}-${group.id}`}
              hidden={collapsedGroups.has(group.id)}
            >
              <ol className="divide-y divide-slate-100">
                {group.topics.map((topic, index) => (
                  <li
                    key={topic.id}
                    className="flex flex-wrap items-center gap-3 px-5 py-4"
                  >
                    <span className="w-5 text-sm tabular-nums text-slate-400">
                      {index + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="break-words font-medium text-slate-800">
                        {topic.title}
                      </p>
                      {topic.description && (
                        <p className="mt-1 line-clamp-2 text-sm text-slate-500">
                          {topic.description}
                        </p>
                      )}
                      {!!topic.related_topic_ids?.length && (
                        <p className="mt-1 text-xs text-indigo-600">
                          {topic.related_topic_ids.length} 个相关知识点
                        </p>
                      )}
                    </div>
                    <div className="flex w-full flex-wrap items-center justify-end gap-2 pl-8 sm:w-auto sm:pl-0">
                      <button
                        disabled={interactionBusy || index === 0}
                        aria-label={`上移${topic.title}`}
                        className={actionClass}
                        onClick={() => moveTopic(group, index, -1)}
                      >
                        ↑
                      </button>
                      <button
                        disabled={
                          interactionBusy || index === group.topics.length - 1
                        }
                        aria-label={`下移${topic.title}`}
                        className={actionClass}
                        onClick={() => moveTopic(group, index, 1)}
                      >
                        ↓
                      </button>
                      <button
                        disabled={interactionBusy}
                        aria-label={`编辑${topic.title}`}
                        className={actionClass}
                        onClick={(event) =>
                          setEditor({ topic, returnFocus: event.currentTarget })
                        }
                      >
                        编辑
                      </button>
                      <button
                        disabled={interactionBusy}
                        aria-label={`删除${topic.title}`}
                        className={`${actionClass} text-rose-700`}
                        onClick={() => setRemoving(topic)}
                      >
                        删除
                      </button>
                    </div>
                  </li>
                ))}
              </ol>
              {!group.topics.length && (
                <p className="px-5 py-6 text-sm text-slate-400">
                  暂无知识点，点击本章的“新增知识点”开始添加。
                </p>
              )}
            </div>
          </section>
        ))}
      </div>
      {!!outline?.removed_topics.length && (
        <details className="mt-8 rounded-2xl border border-slate-200 bg-white p-5">
          <summary className="cursor-pointer text-sm font-medium text-slate-600">
            历史待清理知识点（{outline.removed_topics.length}）
          </summary>
          <ul className="mt-3 divide-y divide-slate-100">
            {outline.removed_topics.map((t) => (
              <li
                key={t.id}
                className="flex items-center justify-between gap-4 py-3 text-sm"
              >
                <span>
                  {t.title}
                  <span className="ml-2 text-slate-400">{t.stage_title}</span>
                </span>
                <button
                  disabled={interactionBusy}
                  aria-label={`永久删除${t.title}`}
                  className={`${actionClass} text-rose-700`}
                  onClick={() => setRemoving(t)}
                >
                  永久删除
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
