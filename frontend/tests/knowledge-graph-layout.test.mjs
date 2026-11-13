import assert from 'node:assert/strict';
import test from 'node:test';
import { layoutGraph, graphNeighbors, stepGraph } from '../lib/knowledge-graph-layout.ts';

const course = (id, sort_order = 1) => ({ id, title: id, sort_order, active: true });
const node = (id, course, order_index = 1) => ({ id, course, title: id, order_index, stage: 1, stage_title: '章节', description: '' });
test('force layout retains owning courses, finite bounds and stable positions across input order', () => {
  const data = { courses: [course('math', 2), course('ml')], nodes: [...Array.from({ length: 120 }, (_, i) => node(`ml.${i}`, 'ml', i)), node('math.a', 'math')], edges: [] };
  const layout = layoutGraph(data);
  assert.equal(layout.nodes.length, 121);
  assert.equal(new Set(layout.nodes.map(n => n.id)).size, 121);
  for (const n of layout.nodes) {
    const c = layout.clusters.find(c => c.id === n.course);
    assert.ok(Number.isFinite(n.x) && Number.isFinite(n.y));
    assert.ok(Math.hypot(n.x - c.x, n.y - c.y) < c.radius);
    assert.ok(n.x > 0 && n.x < layout.width && n.y > 0 && n.y < layout.height);
  }
  for (const a of layout.clusters) for (const b of layout.clusters) {
    if (a.id !== b.id) assert.ok(Math.hypot(a.x - b.x, a.y - b.y) > Math.min(a.radius, b.radius));
  }
  assert.deepEqual(layoutGraph({ ...data, nodes: [...data.nodes].reverse(), courses: [...data.courses].reverse() }), layout);
});
test('actual links attract nodes and degree changes their visual size without invented links', () => {
  const nodes = Array.from({ length: 20 }, (_, i) => node(`ml.${i}`, 'ml', i));
  const data = { courses: [course('ml')], nodes, edges: [] };
  const separate = layoutGraph(data);
  const byId = id => separate.nodes.find(n => n.id === id);
  const a = separate.nodes[0];
  const b = [...separate.nodes].sort((x, y) => Math.hypot(y.x - a.x, y.y - a.y) - Math.hypot(x.x - a.x, x.y - a.y))[0];
  const linked = layoutGraph({ ...data, edges: [{ source: a.id, target: b.id, type: 'related' }] });
  const connectedA = linked.nodes.find(n => n.id === a.id), connectedB = linked.nodes.find(n => n.id === b.id);
  assert.ok(Math.hypot(connectedA.x - connectedB.x, connectedA.y - connectedB.y) < Math.hypot(a.x - b.x, a.y - b.y));
  assert.ok(connectedA.radius > byId(a.id).radius);
  assert.equal(separate.links.length, 0);
  assert.equal(linked.links.length, 1);
  assert.equal(connectedA.degree, 1);
});
test('dragged node stays at the pointer while adjacent nodes relax with no invalid coordinates', () => {
  const data = { courses: [course('ml')], nodes: [node('a', 'ml'), node('b', 'ml')], edges: [{ source: 'a', target: 'b', type: 'related' }] };
  const layout = layoutGraph(data);
  const fixed = layout.nodes[0];
  fixed.fx = fixed.x + 80; fixed.fy = fixed.y - 50;
  const previous = { x: layout.nodes[1].x, y: layout.nodes[1].y };
  for (let i = 0; i < 70; i++) stepGraph(layout, 0.5);
  assert.equal(fixed.x, fixed.fx); assert.equal(fixed.y, fixed.fy);
  assert.ok(Math.hypot(layout.nodes[1].x - previous.x, layout.nodes[1].y - previous.y) > 1);
  assert.ok(layout.nodes.every(n => Number.isFinite(n.x) && Number.isFinite(n.y)));
  assert.equal(layout.links.length, 1);
});
test('adjacency is undirected, keeps isolates and highlights only direct neighbors', () => {
  const data = { courses: [course('ml'), course('math')], nodes: ['a', 'b', 'c', 'isolated'].map(id => node(id, 'ml')), edges: [{ source: 'a', target: 'b' }, { source: 'b', target: 'c' }, { source: 'a', target: 'a' }, { source: 'a', target: 'missing' }] };
  const neighbors = graphNeighbors(data);
  assert.deepEqual([...neighbors.get('a')], ['b']);
  assert.deepEqual([...neighbors.get('b')], ['a', 'c']);
  assert.equal(neighbors.get('isolated').size, 0);
  assert.equal(neighbors.has('missing'), false);
});
test('empty courses and empty graph have finite bounds', () => {
  for (const courses of [[], [course('empty')]]) {
    const layout = layoutGraph({ courses, nodes: [], edges: [] });
    assert.ok(layout.width > 0 && layout.height > 0);
    assert.equal(layout.clusters.length, courses.length);
  }
});
