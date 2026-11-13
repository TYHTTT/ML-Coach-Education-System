"use client";

import { useEffect, useState } from "react";
import { useStudent } from "@/components/StudentProvider";
import { useAdmin } from "@/components/AdminProvider";
import KnowledgeGraphView from "@/components/KnowledgeGraphView";
import { request } from "@/lib/api";
import type { KnowledgeGraphData } from "@/lib/knowledge-graph-layout";

export default function KnowledgeGraphScreen({ admin = false }: { admin?: boolean }) {
  const { withStudent } = useStudent();
  const { withAdmin } = useAdmin();
  const authorize = admin ? withAdmin : withStudent;
  const [data, setData] = useState<KnowledgeGraphData | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setData(null); setError("");
      void authorize(token => request<KnowledgeGraphData>(admin ? "/api/v1/admin/knowledge-graph" : "/api/v1/knowledge-graph", {
        headers: { Authorization: `Bearer ${token}` }, signal: controller.signal,
      })).then(result => { if (!controller.signal.aborted) setData(result); })
        .catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "知识图谱加载失败"); });
    }, 0);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [admin, authorize, revision]);
  return <section aria-label="知识图谱" className="p-3 sm:p-4">
    {error ? <div role="alert" data-admin={admin} className="knowledge-graph grid place-content-center gap-4 p-6 text-center text-sm"><p className="graph-title">{error}</p><button type="button" onClick={() => setRevision(value => value + 1)} className="graph-link mx-auto font-semibold">重试</button></div>
      : !data ? <div role="status" data-admin={admin} className="knowledge-graph grid place-items-center text-sm"><span className="graph-muted">正在加载知识图谱…</span></div>
        : !data.nodes.length ? <div data-admin={admin} className="knowledge-graph grid place-content-center gap-4 p-6 text-center text-sm"><p className="graph-muted">暂无可展示的知识点{admin ? "，请先在课程管理中添加知识点。" : "。"}</p><button type="button" onClick={() => setRevision(value => value + 1)} className="graph-link mx-auto font-semibold">刷新图谱</button></div>
          : <KnowledgeGraphView data={data} admin={admin} onRefresh={() => setRevision(value => value + 1)} />}
  </section>;
}
