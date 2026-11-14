export interface GraphCourse {
  id: string;
  title: string;
  active: boolean;
  sort_order: number;
}
export interface GraphNode {
  id: string;
  course: string;
  title: string;
  description: string;
  stage: number;
  stage_title: string;
  order_index: number;
}
export interface GraphEdge {
  source: string;
  target: string;
  type: string;
}
export interface KnowledgeGraphData {
  courses: GraphCourse[];
  nodes: GraphNode[];
  edges: GraphEdge[];
}
export interface Point {
  x: number;
  y: number;
}
export interface PositionedNode extends GraphNode, Point {}
export interface CourseCluster extends GraphCourse, Point {
  radius: number;
  color: string;
  count: number;
}
export interface ForceNode extends PositionedNode {
  vx: number;
  vy: number;
  anchorX: number;
  anchorY: number;
  radius: number;
  degree: number;
  fx?: number;
  fy?: number;
}
export interface GraphSimulation {
  nodes: ForceNode[];
  links: { source: number; target: number }[];
}

const COLORS = [
  "#a998e8",
  "#75b9ae",
  "#d4ad74",
  "#7fa9d0",
  "#ce91af",
  "#aab874",
  "#a0a8d7",
  "#79b8c8",
];

function seed(id: string) {
  let hash = 2166136261;
  for (let i = 0; i < id.length; i++)
    hash = Math.imul(hash ^ id.charCodeAt(i), 16777619);
  return (hash >>> 0) / 4294967296;
}

/** Springs follow real relations; an invisible course anchor keeps groups together. */
export function stepGraph(simulation: GraphSimulation, alpha = 1) {
  const { nodes, links } = simulation;
  for (let i = 0; i < nodes.length; i++) {
    const a = nodes[i];
    a.vx += (a.anchorX - a.x) * 0.055 * alpha;
    a.vy += (a.anchorY - a.y) * 0.055 * alpha;
    for (let j = i + 1; j < nodes.length; j++) {
      const b = nodes[j];
      const dx = a.x - b.x || 0.01,
        dy = a.y - b.y || 0.01;
      const distance = Math.hypot(dx, dy);
      const separation = a.radius + b.radius + 27;
      const repel =
        (a.course === b.course ? 32 : 20) / Math.max(64, distance * distance);
      const collision = (Math.max(0, separation - distance) * 0.25) / distance;
      const force = (repel + collision) * alpha;
      a.vx += dx * force;
      a.vy += dy * force;
      b.vx -= dx * force;
      b.vy -= dy * force;
    }
  }
  for (const link of links) {
    const a = nodes[link.source],
      b = nodes[link.target];
    const dx = b.x - a.x,
      dy = b.y - a.y;
    const distance = Math.hypot(dx, dy) || 1;
    const sameCourse = a.course === b.course;
    const force =
      ((distance - (sameCourse ? 78 : 170)) / distance) *
      (sameCourse ? 0.09 : 0.035) *
      alpha;
    a.vx += dx * force;
    a.vy += dy * force;
    b.vx -= dx * force;
    b.vy -= dy * force;
  }
  for (const node of nodes) {
    node.vx = Math.max(-18, Math.min(18, node.vx * 0.68));
    node.vy = Math.max(-18, Math.min(18, node.vy * 0.68));
    node.x = node.fx ?? node.x + node.vx;
    node.y = node.fy ?? node.y + node.vy;
    if (node.fx !== undefined) node.vx = node.vy = 0;
  }
}

/** A seeded force layout: no concentric rings, group boundaries or synthetic edges. */
export function layoutGraph(data: KnowledgeGraphData) {
  const courses = [...data.courses].sort(
    (a, b) => a.sort_order - b.sort_order || a.id.localeCompare(b.id),
  );
  const byCourse = new Map(
    courses.map((course) => [course.id, [] as GraphNode[]]),
  );
  for (const node of data.nodes) byCourse.get(node.course)?.push(node);
  const neighbors = graphNeighbors(data);
  const spacing = Math.max(
    200,
    ...courses.map(
      (course) => Math.sqrt(byCourse.get(course.id)!.length) * 35 + 100,
    ),
  );
  const clusters: CourseCluster[] = [];
  const nodes: ForceNode[] = [];
  courses.forEach((course, index) => {
    const items = byCourse
      .get(course.id)!
      .sort(
        (a, b) =>
          a.stage - b.stage ||
          a.order_index - b.order_index ||
          a.id.localeCompare(b.id),
      );
    const orbit = Math.sqrt(index) * spacing;
    const center = {
      x: Math.cos(index * 2.39996 - 0.5) * orbit,
      y: Math.sin(index * 2.39996 - 0.5) * orbit * 0.8,
    };
    const radius = Math.sqrt(items.length) * 24 + 30;
    clusters.push({
      ...course,
      ...center,
      radius,
      color: COLORS[index % COLORS.length],
      count: items.length,
    });
    for (const item of items) {
      const angle = seed(item.id) * Math.PI * 2;
      const distance = Math.sqrt(seed(item.id + ":distance")) * radius;
      const degree = neighbors.get(item.id)?.size ?? 0;
      nodes.push({
        ...item,
        x: center.x + Math.cos(angle) * distance,
        y: center.y + Math.sin(angle) * distance,
        vx: 0,
        vy: 0,
        anchorX: center.x,
        anchorY: center.y,
        degree,
        radius: 3.8 + Math.min(6, Math.sqrt(degree) * 1.5),
      });
    }
  });
  const indices = new Map(nodes.map((node, index) => [node.id, index]));
  const seen = new Set<string>();
  const links: GraphSimulation["links"] = [];
  for (const edge of data.edges) {
    const source = indices.get(edge.source),
      target = indices.get(edge.target);
    const key = [edge.source, edge.target].sort().join(":");
    if (
      source === undefined ||
      target === undefined ||
      source === target ||
      seen.has(key)
    )
      continue;
    seen.add(key);
    links.push({
      source: Math.min(source, target),
      target: Math.max(source, target),
    });
  }
  links.sort((a, b) => a.source - b.source || a.target - b.target);
  const simulation = { nodes, links };
  for (let tick = 0; tick < 220; tick++)
    stepGraph(simulation, Math.max(0.1, 1 - tick / 240));
  const minX = Math.min(0, ...nodes.map((node) => node.x)) - 65;
  const minY = Math.min(0, ...nodes.map((node) => node.y)) - 65;
  for (const node of nodes) {
    node.x -= minX;
    node.y -= minY;
    node.anchorX -= minX;
    node.anchorY -= minY;
  }
  for (const cluster of clusters) {
    cluster.x -= minX;
    cluster.y -= minY;
    cluster.radius = Math.max(
      40,
      ...nodes
        .filter((node) => node.course === cluster.id)
        .map((node) => Math.hypot(node.x - cluster.x, node.y - cluster.y) + 35),
    );
  }
  return {
    clusters,
    nodes,
    links,
    width: Math.max(130, ...nodes.map((node) => node.x + 65)),
    height: Math.max(130, ...nodes.map((node) => node.y + 65)),
  };
}

/** Undirected adjacency includes isolated nodes and only valid visible edges. */
export function graphNeighbors(data: KnowledgeGraphData) {
  const neighbors = new Map(
    data.nodes.map((node) => [node.id, new Set<string>()]),
  );
  for (const edge of data.edges) {
    if (
      edge.source === edge.target ||
      !neighbors.has(edge.source) ||
      !neighbors.has(edge.target)
    )
      continue;
    neighbors.get(edge.source)!.add(edge.target);
    neighbors.get(edge.target)!.add(edge.source);
  }
  return neighbors;
}
