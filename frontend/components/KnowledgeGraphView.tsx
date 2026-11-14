"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  graphNeighbors,
  layoutGraph,
  stepGraph,
  type ForceNode,
  type GraphSimulation,
  type KnowledgeGraphData,
  type Point,
} from "@/lib/knowledge-graph-layout";

interface View {
  x: number;
  y: number;
  scale: number;
}
interface Drag {
  pointerId: number;
  nodeId?: string;
  x: number;
  y: number;
  initial: View;
  moved: boolean;
}
const glyphs = {
  search: "m21 21-5-5M19 11a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z",
  refresh: "M20 7v5h-5M4 17v-5h5M6 6a8 8 0 0 1 13 3M18 18A8 8 0 0 1 5 15",
  fit: "M8 3H3v5M16 3h5v5M21 16v5h-5M8 21H3v-5M8 8h8v8H8Z",
  plus: "M12 5v14M5 12h14",
  minus: "M5 12h14",
  sun: "M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.4 1.4M17.6 17.6 19 19M5 19l1.4-1.4M17.6 6.4 19 5M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z",
  moon: "M20.9 13A9 9 0 0 1 11 3.1 9 9 0 1 0 20.9 13Z",
  close: "m6 6 12 12M6 18 18 6",
  expand: "M8 3H3v5M16 3h5v5M21 16v5h-5M8 21H3v-5",
};
function Glyph({ name }: { name: keyof typeof glyphs }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="size-4"
    >
      <path d={glyphs[name]} />
    </svg>
  );
}

function fitNodes(
  nodes: Point[],
  size: { width: number; height: number },
): View {
  const left = Math.min(...nodes.map((node) => node.x)) - 75,
    top = Math.min(...nodes.map((node) => node.y)) - 65;
  const width = Math.max(...nodes.map((node) => node.x)) - left + 130;
  const height = Math.max(...nodes.map((node) => node.y)) - top + 65;
  const scale = Math.max(
    0.03,
    Math.min((size.width - 40) / width, (size.height - 180) / height, 1.7),
  );
  return {
    scale,
    x: (size.width - width * scale) / 2 - left * scale,
    y: 100 + (size.height - 180 - height * scale) / 2 - top * scale,
  };
}

export default function KnowledgeGraphView({
  data,
  admin,
  onRefresh,
}: {
  data: KnowledgeGraphData;
  admin: boolean;
  onRefresh: () => void;
}) {
  const layout = useMemo(() => layoutGraph(data), [data]);
  const [positions, setPositions] = useState(layout.nodes);
  const nodesById = useMemo(
    () => new Map(positions.map((node) => [node.id, node])),
    [positions],
  );
  const coursesById = useMemo(
    () => new Map(layout.clusters.map((course) => [course.id, course])),
    [layout],
  );
  const neighbors = useMemo(() => graphNeighbors(data), [data]);
  const root = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLDivElement>(null);
  const drag = useRef<Drag | null>(null);
  const simulation = useRef<GraphSimulation | null>(null);
  const animation = useRef(0);
  const framesLeft = useRef(0);
  const [size, setSize] = useState({ width: 1200, height: 760 });
  const [customView, setCustomView] = useState<View | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const [focused, setFocused] = useState<string | null>(null);
  const [pinned, setPinned] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [labels, setLabels] = useState(true);
  const [dark, setDark] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const activeId = hovered ?? focused ?? pinned;
  const related = activeId ? neighbors.get(activeId) : undefined;
  const detail = nodesById.get(focused ?? pinned ?? "");
  const fit = useMemo(() => fitNodes(positions, size), [positions, size]);
  const view = customView ?? fit;
  const matches = useMemo(() => {
    const term = query.trim().toLocaleLowerCase();
    return term
      ? positions.filter((node) =>
          `${node.title} ${node.id} ${coursesById.get(node.course)?.title}`
            .toLocaleLowerCase()
            .includes(term),
        )
      : [];
  }, [query, positions, coursesById]);
  const matchIds = useMemo(
    () => new Set(matches.map((node) => node.id)),
    [matches],
  );
  const visibleLabels = useMemo(() => {
    const occupied: { x: number; y: number; width: number }[] = [];
    const visible = new Set<string>();
    const dots = positions.map((node) => ({
      id: node.id,
      x: node.x * view.scale + view.x,
      y: node.y * view.scale + view.y,
    }));
    const priority = (node: ForceNode) =>
      (node.id === activeId ? 10000 : related?.has(node.id) ? 5000 : 0) +
      (matchIds.has(node.id) ? 1000 : 0) +
      node.degree;
    for (const node of [...positions].sort(
      (a, b) => priority(b) - priority(a),
    )) {
      const important =
        node.id === activeId || related?.has(node.id) || matchIds.has(node.id);
      if (!important && (!labels || view.scale < 0.42)) continue;
      const box = {
        x:
          node.x * view.scale +
          view.x +
          Math.max(node.radius * view.scale, 3) +
          7,
        y: node.y * view.scale + view.y,
        width: Math.min(node.title.length, 15) * 10.5 + 8,
      };
      if (
        box.x < 0 ||
        box.x > size.width ||
        box.y < 90 ||
        box.y > size.height - 45
      )
        continue;
      if (
        !important &&
        dots.some(
          (dot) =>
            dot.id !== node.id &&
            Math.abs(dot.y - box.y) < 9 &&
            dot.x > box.x - 3 &&
            dot.x < box.x + box.width,
        )
      )
        continue;
      if (
        important ||
        !occupied.some(
          (other) =>
            Math.abs(other.y - box.y) < 18 &&
            box.x < other.x + other.width &&
            box.x + box.width > other.x,
        )
      ) {
        visible.add(node.id);
        occupied.push(box);
      }
    }
    return visible;
  }, [positions, activeId, related, matchIds, labels, view, size]);

  useEffect(() => {
    simulation.current = {
      nodes: layout.nodes.map((node) => ({ ...node })),
      links: layout.links,
    };
    const element = canvas.current;
    const observer = new ResizeObserver(([entry]) =>
      setSize({
        width: entry.contentRect.width,
        height: entry.contentRect.height,
      }),
    );
    if (element) observer.observe(element);
    const changed = () =>
      setFullscreen(document.fullscreenElement === root.current);
    document.addEventListener("fullscreenchange", changed);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(animation.current);
      animation.current = 0;
      simulation.current = null;
      document.removeEventListener("fullscreenchange", changed);
    };
  }, [layout]);

  function relax() {
    framesLeft.current = 70;
    if (animation.current) return;
    const frame = () => {
      if (!simulation.current) return;
      stepGraph(simulation.current, Math.max(0.08, framesLeft.current / 70));
      setPositions(simulation.current.nodes.map((node) => ({ ...node })));
      framesLeft.current--;
      animation.current =
        framesLeft.current > 0 ? requestAnimationFrame(frame) : 0;
    };
    animation.current = requestAnimationFrame(frame);
  }
  const zoom = useCallback(
    (factor: number, point?: Point) => {
      const anchor = point ?? { x: size.width / 2, y: size.height / 2 };
      setCustomView((previous) => {
        const current = previous ?? fit;
        const scale = Math.max(
          fit.scale * 0.25,
          Math.min(5, current.scale * factor),
        );
        const ratio = scale / current.scale;
        return {
          scale,
          x: anchor.x - (anchor.x - current.x) * ratio,
          y: anchor.y - (anchor.y - current.y) * ratio,
        };
      });
    },
    [fit, size],
  );
  useEffect(() => {
    const element = canvas.current;
    if (!element) return;
    const wheel = (event: WheelEvent) => {
      event.preventDefault();
      const bounds = element.getBoundingClientRect();
      zoom(Math.exp(-Math.max(-100, Math.min(100, event.deltaY)) * 0.004), {
        x: event.clientX - bounds.left,
        y: event.clientY - bounds.top,
      });
    };
    element.addEventListener("wheel", wheel, { passive: false });
    return () => element.removeEventListener("wheel", wheel);
  }, [zoom]);

  function clearSelection() {
    setPinned(null);
    setHovered(null);
    setFocused(null);
  }
  function select(node: ForceNode) {
    setPinned(node.id);
    setHovered(null);
    setFocused(null);
    setQuery("");
    const scale = Math.max(view.scale, Math.min(1.5, size.width / 450));
    setCustomView({
      scale,
      x: size.width / 2 - node.x * scale,
      y: size.height * 0.42 - node.y * scale,
    });
  }
  async function toggleFullscreen() {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await root.current?.requestFullscreen();
    } catch {
      /* Keep the current view when fullscreen is unavailable. */
    }
  }
  function tone(color: string) {
    return dark ? color : `color-mix(in srgb, ${color} 65%, #282333)`;
  }

  return (
    <div
      ref={root}
      data-graph-theme={dark ? "dark" : "light"}
      data-admin={admin}
      className="knowledge-graph"
    >
      <div className="pointer-events-none absolute inset-x-4 top-4 z-10 flex items-start justify-between gap-3 sm:inset-x-6 sm:top-5">
        <div>
          <h1 className="graph-title text-sm font-semibold">知识图谱</h1>
          <p className="graph-muted mt-1 whitespace-nowrap text-[10px] sm:text-[11px]">
            <span className="hidden sm:inline">
              {data.courses.length} 门课程
              <span className="mx-2 opacity-40">/</span>
            </span>
            {data.nodes.length} 个知识点
            <span className="mx-2 opacity-40">/</span>
            {data.edges.length} 条关联
          </p>
        </div>
        <div className="graph-panel pointer-events-auto flex items-center gap-0.5 rounded-lg p-1">
          <button
            type="button"
            onClick={() => setLabels((value) => !value)}
            title="显示名称"
            aria-label="显示名称"
            aria-pressed={labels}
            className="graph-tool text-xs font-medium"
          >
            Aa
          </button>
          <button
            type="button"
            onClick={() => setDark((value) => !value)}
            aria-label={dark ? "切换浅色图谱" : "切换深色图谱"}
            title={dark ? "切换浅色图谱" : "切换深色图谱"}
            className="graph-tool"
          >
            <Glyph name={dark ? "sun" : "moon"} />
          </button>
          <button
            type="button"
            onClick={onRefresh}
            aria-label="刷新图谱"
            title="刷新图谱"
            className="graph-tool"
          >
            <Glyph name="refresh" />
          </button>
          <button
            type="button"
            onClick={() => void toggleFullscreen()}
            aria-label={fullscreen ? "退出全屏" : "全屏图谱"}
            title={fullscreen ? "退出全屏" : "全屏图谱"}
            className="graph-tool graph-fullscreen"
          >
            <Glyph name="expand" />
          </button>
        </div>
      </div>

      <div className="absolute left-4 top-20 z-20 w-[min(280px,calc(100%-32px))] sm:left-6">
        <div className="graph-panel graph-search flex items-center gap-2 rounded-lg px-3">
          <Glyph name="search" />
          <label htmlFor="graph-search" className="sr-only">
            搜索知识点
          </label>
          <input
            id="graph-search"
            type="search"
            autoComplete="off"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") setQuery("");
            }}
            placeholder="搜索知识点…"
            className="min-w-0 flex-1 bg-transparent py-2.5 text-xs outline-none"
          />
        </div>
        {query.trim() && (
          <div
            aria-label="搜索结果"
            className="graph-panel mt-2 max-h-72 overflow-y-auto rounded-lg p-1"
          >
            {matches.length ? (
              matches.map((node) => (
                <button
                  key={node.id}
                  type="button"
                  onClick={() => select(node)}
                  className="graph-result block w-full rounded-md px-3 py-2.5 text-left"
                >
                  <span className="graph-title block text-xs font-medium">
                    {node.title}
                  </span>
                  <span className="graph-muted mt-1 block text-[10px]">
                    {coursesById.get(node.course)?.title} · {node.id}
                  </span>
                </button>
              ))
            ) : (
              <p className="graph-muted p-3 text-xs">没有匹配的知识点</p>
            )}
          </div>
        )}
      </div>

      <div
        ref={canvas}
        data-graph-canvas
        className="absolute inset-0 overflow-hidden"
        style={{ touchAction: "none" }}
      >
        <svg
          role="group"
          aria-label="课程知识图谱，悬停高亮关联，可拖动节点和画布"
          width="100%"
          height="100%"
          className="graph-canvas"
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              clearSelection();
              (event.target as SVGElement).blur();
            }
            if (event.key === "+" || event.key === "=") {
              event.preventDefault();
              zoom(1.25);
            }
            if (event.key === "-") {
              event.preventDefault();
              zoom(0.8);
            }
          }}
          onPointerDown={(event) => {
            if (event.button !== 0) return;
            const nodeId =
              (event.target as Element)
                .closest("[data-node-id]")
                ?.getAttribute("data-node-id") ?? undefined;
            drag.current = {
              pointerId: event.pointerId,
              nodeId,
              x: event.clientX,
              y: event.clientY,
              initial: view,
              moved: false,
            };
            setCustomView(view);
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerMove={(event) => {
            const current = drag.current;
            if (!current || current.pointerId !== event.pointerId) return;
            const dx = event.clientX - current.x,
              dy = event.clientY - current.y;
            if (Math.hypot(dx, dy) > 4) current.moved = true;
            if (!current.moved) return;
            if (current.nodeId && simulation.current) {
              const bounds = event.currentTarget.getBoundingClientRect();
              const node = simulation.current.nodes.find(
                (node) => node.id === current.nodeId,
              )!;
              node.x = node.fx =
                (event.clientX - bounds.left - current.initial.x) /
                current.initial.scale;
              node.y = node.fy =
                (event.clientY - bounds.top - current.initial.y) /
                current.initial.scale;
              setHovered(node.id);
              relax();
            } else {
              setHovered(null);
              setCustomView({
                ...current.initial,
                x: current.initial.x + dx,
                y: current.initial.y + dy,
              });
            }
          }}
          onPointerUp={(event) => {
            const current = drag.current;
            if (!current || current.pointerId !== event.pointerId) return;
            if (!current.moved) {
              if (current.nodeId)
                setPinned((previous) =>
                  previous === current.nodeId ? null : current.nodeId!,
                );
              else clearSelection();
            }
            drag.current = null;
            if (event.currentTarget.hasPointerCapture(event.pointerId))
              event.currentTarget.releasePointerCapture(event.pointerId);
          }}
          onPointerCancel={() => {
            drag.current = null;
            setHovered(null);
          }}
        >
          <g
            data-graph-transform
            transform={`translate(${view.x} ${view.y}) scale(${view.scale})`}
          >
            {data.edges.map((edge) => {
              const source = nodesById.get(edge.source),
                target = nodesById.get(edge.target);
              if (!source || !target) return null;
              const highlighted =
                activeId === source.id || activeId === target.id;
              return (
                <path
                  key={`${edge.source}:${edge.target}`}
                  data-edge-source={source.id}
                  data-edge-target={target.id}
                  data-highlighted={highlighted}
                  d={`M${source.x},${source.y} L${target.x},${target.y}`}
                  className="graph-edge"
                  fill="none"
                  stroke={
                    highlighted ? "var(--graph-accent)" : "var(--graph-line)"
                  }
                  strokeWidth={highlighted ? 1.5 : 0.75}
                  strokeOpacity={activeId ? (highlighted ? 0.9 : 0.045) : 0.5}
                  vectorEffect="non-scaling-stroke"
                  pointerEvents="none"
                />
              );
            })}
            {positions.map((node) => {
              const highlighted =
                activeId === node.id || !!related?.has(node.id);
              const faded = activeId
                ? !highlighted
                : query.trim()
                  ? !matchIds.has(node.id)
                  : false;
              const color = tone(coursesById.get(node.course)!.color);
              const radius = Math.max(node.radius, 2.5 / view.scale);
              const primary = activeId === node.id;
              return (
                <g
                  key={node.id}
                  data-node-id={node.id}
                  data-course-id={node.course}
                  data-highlighted={highlighted}
                  role="button"
                  tabIndex={0}
                  aria-label={`${node.title}，${coursesById.get(node.course)?.title}，${node.degree} 个关联知识点`}
                  aria-pressed={pinned === node.id}
                  className="graph-node outline-none"
                  opacity={faded ? 0.12 : 1}
                  onPointerEnter={(event) => {
                    if (event.pointerType === "mouse" && !drag.current)
                      setHovered(node.id);
                  }}
                  onPointerLeave={() => {
                    if (!drag.current?.nodeId) setHovered(null);
                  }}
                  onFocus={() => setFocused(node.id)}
                  onBlur={() => setFocused(null)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setPinned((previous) =>
                        previous === node.id ? null : node.id,
                      );
                    }
                  }}
                >
                  <title>
                    {node.title} · {coursesById.get(node.course)?.title}
                  </title>
                  <circle
                    cx={node.x}
                    cy={node.y}
                    r={Math.max(radius + 5 / view.scale, 9 / view.scale)}
                    fill="transparent"
                  />
                  {primary && (
                    <circle
                      cx={node.x}
                      cy={node.y}
                      r={radius + 5 / view.scale}
                      fill="none"
                      stroke="var(--graph-accent)"
                      strokeOpacity="0.3"
                      strokeWidth="1"
                      vectorEffect="non-scaling-stroke"
                      pointerEvents="none"
                    />
                  )}
                  <circle
                    data-node-dot
                    cx={node.x}
                    cy={node.y}
                    r={primary ? radius + 1 / view.scale : radius}
                    fill={primary ? "var(--graph-accent)" : color}
                    pointerEvents="none"
                  />
                  {visibleLabels.has(node.id) && (
                    <text
                      x={node.x + radius + 7 / view.scale}
                      y={node.y}
                      dy=".35em"
                      fontSize={11 / view.scale}
                      fill={
                        highlighted ? "var(--graph-text)" : "var(--graph-label)"
                      }
                      fillOpacity={
                        highlighted || matchIds.has(node.id)
                          ? 1
                          : Math.min(0.85, Math.max(0.35, view.scale - 0.1))
                      }
                      stroke="var(--graph-bg)"
                      strokeWidth={3 / view.scale}
                      paintOrder="stroke"
                      pointerEvents="none"
                    >
                      {node.title.length > 15
                        ? `${node.title.slice(0, 15)}…`
                        : node.title}
                    </text>
                  )}
                </g>
              );
            })}
          </g>
        </svg>
      </div>

      {detail ? (
        <aside
          aria-label="知识点详情"
          className="graph-panel absolute bottom-5 left-4 z-10 max-h-[min(380px,55%)] w-[min(310px,calc(100%-88px))] overflow-y-auto rounded-xl p-4 sm:bottom-6 sm:left-6"
        >
          <div className="flex items-start justify-between gap-2">
            <p
              className="text-[11px]"
              style={{ color: tone(coursesById.get(detail.course)!.color) }}
            >
              {coursesById.get(detail.course)?.title}
              {!coursesById.get(detail.course)?.active && " · 已停用"}
            </p>
            <button
              type="button"
              onClick={clearSelection}
              className="graph-tool -mr-1 -mt-1 !size-6"
              aria-label="取消选择"
            >
              <Glyph name="close" />
            </button>
          </div>
          <h2 className="graph-title mt-1 break-words text-sm font-semibold">
            {detail.title}
          </h2>
          <p className="graph-muted mt-1 break-all text-[10px]">{detail.id}</p>
          {detail.description && (
            <p className="graph-secondary mt-3 line-clamp-3 text-xs leading-5">
              {detail.description}
            </p>
          )}
          <div className="graph-divider my-3 border-t" />
          <h3 className="graph-muted text-[10px]">
            相关知识点 · {neighbors.get(detail.id)?.size ?? 0}
          </h3>
          <div className="mt-2 flex max-h-24 flex-wrap gap-1.5 overflow-y-auto">
            {[...(neighbors.get(detail.id) ?? [])].map((id) => (
              <button
                key={id}
                type="button"
                onClick={() => select(nodesById.get(id)!)}
                className="graph-chip rounded-md px-2 py-1 text-[11px]"
              >
                {nodesById.get(id)?.title}
              </button>
            ))}
          </div>
          {!neighbors.get(detail.id)?.size && (
            <p className="graph-muted mt-1 text-xs">尚未设置关联</p>
          )}
          <Link
            href={
              admin
                ? `/admin/courses/${detail.course}`
                : `/learn/${detail.course}/${detail.id}`
            }
            className="graph-link mt-4 inline-flex items-center gap-1 text-xs font-medium"
          >
            {admin ? "查看课程" : "学习此知识点"}
            <span aria-hidden="true">↗</span>
          </Link>
        </aside>
      ) : (
        <div className="absolute bottom-5 left-4 z-10 max-w-[calc(100%-85px)] sm:bottom-6 sm:left-6">
          {!data.edges.length && (
            <p className="graph-muted mb-3 text-[10px]">尚未设置知识点关联</p>
          )}
          <div
            aria-label="课程图例"
            className="flex flex-wrap gap-x-4 gap-y-2.5"
          >
            {layout.clusters.map((course) => (
              <button
                key={course.id}
                type="button"
                aria-label={`定位${course.title}`}
                onClick={() => {
                  clearSelection();
                  const points = positions.filter(
                    (node) => node.course === course.id,
                  );
                  if (points.length) setCustomView(fitNodes(points, size));
                }}
                className="graph-legend inline-flex items-center gap-1.5 text-[10px] sm:text-[11px]"
              >
                <span
                  className="size-1.5 rounded-full"
                  style={{ background: tone(course.color) }}
                />
                {course.title}
                <span className="graph-muted ml-0.5 text-[10px]">
                  {course.count}
                  {!course.active && " · 停用"}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      <p className="graph-muted pointer-events-none absolute bottom-6 left-1/2 hidden -translate-x-1/2 text-[10px] xl:block">
        拖动节点或画布<span className="mx-2 opacity-40">·</span>滚轮缩放
      </p>
      <div
        className="graph-panel absolute bottom-5 right-4 z-10 flex flex-col rounded-lg p-1 sm:bottom-6 sm:right-6"
        aria-label="图谱视图控制"
      >
        <button
          type="button"
          onClick={() => zoom(1.25)}
          aria-label="放大图谱"
          title="放大图谱"
          className="graph-tool"
        >
          <Glyph name="plus" />
        </button>
        <button
          type="button"
          onClick={() => zoom(0.8)}
          aria-label="缩小图谱"
          title="缩小图谱"
          className="graph-tool"
        >
          <Glyph name="minus" />
        </button>
        <div className="graph-divider mx-1 my-1 border-t" />
        <button
          type="button"
          onClick={() => {
            setCustomView(null);
            clearSelection();
            setQuery("");
          }}
          aria-label="适应画布"
          title="适应画布"
          className="graph-tool"
        >
          <Glyph name="fit" />
        </button>
      </div>
    </div>
  );
}
