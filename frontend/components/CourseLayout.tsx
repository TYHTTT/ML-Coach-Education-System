"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type KeyboardEvent,
} from "react";
import { useStudent } from "./StudentProvider";
import { getCourseOutline } from "@/lib/api";
import type { Course } from "@/lib/types";
import { useCourseCatalog } from "@/components/CourseCatalogProvider";
import type { CourseOutline, OutlineGroup, OutlineTopic } from "@/lib/types";
import { statusMeta } from "@/lib/learning";

type CourseContext = {
  outline: CourseOutline | null;
  course: Course | null;
  refresh: () => Promise<void>;
  topicHref: (topic: Pick<OutlineTopic, "topic_id">) => string;
};
const OutlineContext = createContext<CourseContext>({
  outline: null,
  course: null,
  refresh: async () => {},
  topicHref: () => "/learn",
});
export const useCourseOutline = () => useContext(OutlineContext);
/** Keep the current course directory mounted while switching knowledge points. */
export default function CourseLayout({ children }: { children: ReactNode }) {
  const params = useParams<{ course?: string; topicId?: string }>();
  const rawCourse = params.course;
  const { courses } = useCourseCatalog();
  const course = courses.find((item) => item.id === rawCourse)?.id ?? null;
  const courseName = (id: string) =>
    courses.find((item) => item.id === id)?.title ?? id;
  const topicId = params.topicId ? decodeURIComponent(params.topicId) : "";
  const { status, withStudent, studentId } = useStudent();
  const [outline, setOutline] = useState<CourseOutline | null>(null);
  const [error, setError] = useState("");
  const currentOutline = outline?.course === course ? outline : null;
  const [query, setQuery] = useState("");
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [closedGroups, setClosedGroups] = useState<string[]>([]);
  const [lastTopic, setLastTopic] = useState("");
  const navRef = useRef<HTMLElement>(null);
  const mobileButton = useRef<HTMLButtonElement>(null);
  const previousTopic = useRef("");
  const outlineRequest = useRef(0);
  const refresh = useCallback(async () => {
    if (!course) return;
    const requestId = ++outlineRequest.current;
    try {
      const value = await withStudent((id) => getCourseOutline(course, id));
      if (requestId === outlineRequest.current) {
        setOutline(value);
        setError("");
      }
    } catch (cause) {
      if (requestId === outlineRequest.current)
        setError(
          cause instanceof Error ? cause.message : "目录加载失败，请重试。",
        );
    }
  }, [course, withStudent]);
  useEffect(() => {
    if (status !== "ready") return;
    const timer = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timer);
  }, [refresh, status, studentId]);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      try {
        const saved = JSON.parse(
          window.localStorage.getItem(`course-coach:outline:${course}`) || "{}",
        );
        setClosedGroups(Array.isArray(saved.closed) ? saved.closed : []);
        setCollapsed(Boolean(saved.collapsed));
        setLastTopic(
          typeof saved.lastTopic === "string" &&
            saved.lastTopic.startsWith(`/learn/${course}/`)
            ? saved.lastTopic.split("?")[0]
            : "",
        );
      } catch {
        /* Directory remains usable without browser storage. */
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, [course]);
  useEffect(() => {
    if (
      !currentOutline ||
      !topicId ||
      previousTopic.current === `${course}:${topicId}`
    )
      return;
    previousTopic.current = `${course}:${topicId}`;
    const group = currentOutline.groups.find((entry) =>
      entry.topics.some((topic) => topic.topic_id === topicId),
    );
    const timer = window.setTimeout(() => {
      setClosedGroups((current) =>
        current.filter(
          (id) => id !== group?.id && id !== group?.parent_group_id,
        ),
      );
      setMobileOpen(false);
      try {
        const prior = JSON.parse(
          window.localStorage.getItem(`course-coach:outline:${course}`) || "{}",
        );
        window.localStorage.setItem(
          `course-coach:outline:${course}`,
          JSON.stringify({ ...prior, lastTopic: window.location.pathname }),
        );
      } catch {
        /* URL is the authoritative current location. */
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, [currentOutline, topicId, course]);
  useEffect(() => {
    if (!mobileOpen) return;
    const priorOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    navRef.current?.querySelector<HTMLElement>("button, input, a")?.focus();
    return () => {
      document.body.style.overflow = priorOverflow;
    };
  }, [mobileOpen]);
  function persist(closed: string[], isCollapsed: boolean) {
    try {
      window.localStorage.setItem(
        `course-coach:outline:${course}`,
        JSON.stringify({
          closed,
          collapsed: isCollapsed,
          lastTopic: topicId ? window.location.pathname : lastTopic,
        }),
      );
    } catch {
      /* Optional UI preference. */
    }
  }
  const topicHref = useCallback(
    (topic: Pick<OutlineTopic, "topic_id">) =>
      course
        ? `/learn/${course}/${encodeURIComponent(topic.topic_id)}`
        : "/learn",
    [course],
  );
  const value = useMemo(
    () => ({ outline: currentOutline, course, refresh, topicHref }),
    [currentOutline, course, refresh, topicHref],
  );
  if (!course)
    return (
      <OutlineContext.Provider value={value}>
        {children}
      </OutlineContext.Provider>
    );
  function closeMobile() {
    setMobileOpen(false);
    mobileButton.current?.focus();
  }
  function navigateKeyboard(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "Escape" && mobileOpen) {
      closeMobile();
      return;
    }
    const all = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>("a,button,input"),
    ).filter((item) => item.offsetParent !== null);
    const active = document.activeElement as HTMLElement;
    const index = all.indexOf(active);
    if (event.key === "Tab" && mobileOpen) {
      if (!event.shiftKey && index === all.length - 1) {
        event.preventDefault();
        all[0]?.focus();
      }
      if (event.shiftKey && index === 0) {
        event.preventDefault();
        all.at(-1)?.focus();
      }
    }
    if (active?.tagName === "INPUT") return;
    if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
      event.preventDefault();
      const next =
        event.key === "Home"
          ? 0
          : event.key === "End"
            ? all.length - 1
            : Math.max(
                0,
                Math.min(
                  all.length - 1,
                  index + (event.key === "ArrowDown" ? 1 : -1),
                ),
              );
      all[next]?.focus();
    }
  }
  const groups = currentOutline?.groups ?? [];
  const matches = (topic: OutlineTopic) =>
    `${topic.title} ${topic.description}`
      .toLowerCase()
      .includes(query.toLowerCase());
  function renderGroup(group: OutlineGroup) {
    const children = groups.filter((item) => item.parent_group_id === group.id);
    const visibleTopics = group.topics.filter(matches);
    const childHasMatch = children.some((child) => child.topics.some(matches));
    if (query && !visibleTopics.length && !childHasMatch) return null;
    const opened = Boolean(query) || !closedGroups.includes(group.id);
    const allTopics = [
      ...group.topics,
      ...children.flatMap((child) => child.topics),
    ];
    return (
      <section key={group.id} className="mt-2">
        <button
          type="button"
          aria-expanded={opened}
          aria-controls={`group-${group.id}`}
          onClick={() => {
            const next = opened
              ? [...closedGroups, group.id]
              : closedGroups.filter((id) => id !== group.id);
            setClosedGroups(next);
            persist(next, collapsed);
          }}
          className="flex w-full items-center gap-2 rounded-lg px-2 py-2.5 text-left text-xs font-bold text-slate-700 hover:bg-slate-100"
        >
          <span aria-hidden="true">{opened ? "▾" : "▸"}</span>
          <span className="flex-1">{group.title}</span>
          <span className="shrink-0 font-normal tabular-nums text-slate-400">
            {allTopics.filter((topic) => topic.status === "mastered").length}/
            {allTopics.length}
          </span>
        </button>
        {opened && (
          <div
            id={`group-${group.id}`}
            className="ml-3 border-l border-slate-200/80 pl-2"
          >
            {visibleTopics.map((topic) => {
              const state = statusMeta(topic.status);
              const active = topic.topic_id === topicId;
              return (
                <Link
                  key={topic.topic_id}
                  href={topicHref(topic)}
                  prefetch={false}
                  aria-current={active ? "page" : undefined}
                  onClick={closeMobile}
                  className={`my-1 block rounded-xl border px-3 py-2.5 text-sm ${active ? "border-indigo-200 bg-indigo-50 text-indigo-900" : "border-transparent text-slate-600 hover:bg-slate-50"}`}
                >
                  <span className="block font-medium">{topic.title}</span>
                  <span className="mt-1 block text-[10px] text-slate-500">
                    <span aria-hidden="true">{state.symbol}</span> {state.label}
                  </span>
                </Link>
              );
            })}
            {children.map(renderGroup)}
          </div>
        )}
      </section>
    );
  }
  const recommended = groups
    .flatMap((group) => group.topics)
    .find((topic) => topic.topic_id === currentOutline?.recommended_topic_id);
  return (
    <OutlineContext.Provider value={value}>
      <div className="border-b border-slate-200 bg-white px-4 py-2 lg:hidden">
        <button
          ref={mobileButton}
          type="button"
          aria-expanded={mobileOpen}
          aria-controls="course-outline"
          onClick={() => setMobileOpen(true)}
          className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold"
        >
          ☰ 课程目录
        </button>
      </div>
      <div className="mx-auto flex max-w-[1600px] items-start">
        {mobileOpen && (
          <button
            type="button"
            tabIndex={-1}
            onClick={closeMobile}
            aria-label="关闭目录遮罩"
            className="fixed inset-0 z-40 bg-slate-950/40 lg:hidden"
          />
        )}
        <aside
          ref={navRef}
          id="course-outline"
          aria-label="课程知识点目录"
          onKeyDown={navigateKeyboard}
          className={`${mobileOpen ? "fixed inset-y-0 left-0 z-50 flex w-[min(290px,85vw)]" : "hidden"} ${collapsed ? "lg:w-14" : "lg:w-[280px]"} shrink-0 flex-col border-r border-slate-200 bg-white lg:sticky lg:top-[65px] lg:flex lg:h-[calc(100svh-65px)]`}
        >
          <div className="flex items-center justify-between border-b border-slate-100 p-3">
            {(!collapsed || mobileOpen) && (
              <Link
                href={`/learn/${course}`}
                className="min-w-0 text-sm font-bold"
              >
                {courseName(course)}
              </Link>
            )}
            <button
              type="button"
              aria-label={collapsed ? "展开课程目录" : "折叠课程目录"}
              onClick={() => {
                setCollapsed(!collapsed);
                persist(closedGroups, !collapsed);
              }}
              className="hidden rounded-lg px-2 py-1 text-slate-500 lg:block"
            >
              {collapsed ? "»" : "«"}
            </button>
            <button
              type="button"
              onClick={closeMobile}
              className="rounded-lg px-2 py-1 text-sm lg:hidden"
              aria-label="关闭课程目录"
            >
              ✕
            </button>
          </div>
          {(!collapsed || mobileOpen) && (
            <div className="chat-scrollbar min-h-0 flex-1 overflow-y-auto p-3">
              <label
                className="block text-xs font-medium text-slate-500"
                htmlFor="topic-search"
              >
                搜索知识点
              </label>
              <input
                id="topic-search"
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="例如：梯度、内积"
                className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm"
              />
              {recommended && !query && (
                <Link
                  prefetch={false}
                  href={topicHref(recommended)}
                  className="mt-3 block rounded-xl bg-indigo-50 p-3 text-xs text-indigo-800"
                >
                  <span className="block font-bold">建议学习</span>
                  <span className="mt-1 block">{recommended.title} →</span>
                </Link>
              )}
              {!topicId && lastTopic && (
                <Link
                  href={lastTopic}
                  className="mt-3 block text-xs font-semibold text-indigo-700"
                >
                  返回上次阅读位置 →
                </Link>
              )}
              {error && (
                <div role="alert" className="mt-3 text-xs text-rose-700">
                  {error}
                  <button
                    type="button"
                    onClick={() => void refresh()}
                    className="ml-2 underline"
                  >
                    重新加载目录
                  </button>
                </div>
              )}
              {!outline && !error && (
                <p role="status" className="mt-5 text-xs text-slate-400">
                  正在读取目录…
                </p>
              )}
              {groups
                .filter((group) => !group.parent_group_id)
                .map(renderGroup)}
              {query && !groups.some((group) => group.topics.some(matches)) && (
                <p className="py-5 text-xs text-slate-500">
                  没有匹配知识点，试试缩短关键词。
                </p>
              )}
              <div className="mt-6 flex gap-4 border-t border-slate-100 pt-4 text-xs text-slate-500">
                <Link href="/learn">切换课程</Link>
              </div>
            </div>
          )}
        </aside>
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </OutlineContext.Provider>
  );
}
