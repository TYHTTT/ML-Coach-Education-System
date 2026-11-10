// Browser regression uses mocked API responses and an isolated login session.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const { chromium } = createRequire(import.meta.url)(process.env.COURSE_PLAYWRIGHT_MODULE || "playwright");
const baseUrl = process.env.COURSE_UI_BASE_URL || "http://127.0.0.1:3030";
const browser = await chromium.launch({ headless: true, ...(process.env.COURSE_BROWSER_PATH ? { executablePath: process.env.COURSE_BROWSER_PATH } : {}) });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
await context.addInitScript(() => {
  localStorage.setItem("course_coach_access_token", "browser-test-token");
  localStorage.setItem("course_coach_student_profile", JSON.stringify({ student_id: "browser-student", username: "test", display_name: "测试" }));
});
const page = await context.newPage();
const problems = [];
const requests = [];
page.on("pageerror", (error) => problems.push(error.message));
const topics = [
  { id: "ml.machine_learning_basics", title: "机器学习基础" },
  { id: "ml.supervised_learning", title: "监督学习与无监督学习" },
].map((item, index) => ({ ...item, topic_id: item.id, course: "machine_learning", owner_course: "machine_learning", description: "理解数据驱动建模的流程与基本概念。", learning_objectives: ["理解训练数据与模型的关系", "区分分类与回归任务"], stage: 1, stage_title: "机器学习基础", order_index: index, status: "learning", mastery: null, confidence: null, evidence_count: 0, prerequisites: [], prerequisite_gap: [], is_reference: false, required_dimensions: ["concept"], dimensions: [] }));
const instances = new Map();
let serial = 0;
let chatFailure = false;
const answer = "监督学习使用带标签的数据训练模型。";
const json = (route, payload, status = 200) => route.fulfill({ status, contentType: "application/json", headers: { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*", "Access-Control-Allow-Methods": "*" }, body: JSON.stringify(payload) });
await page.route("**/api/v1/**", async (route) => {
  const request = route.request();
  const endpoint = new URL(request.url()).pathname;
  const body = request.postDataJSON() || {};
  requests.push({ endpoint, body });
  if (request.method() === "OPTIONS") return json(route, {});
  if (endpoint.endsWith("/outline")) return json(route, { course: "machine_learning", title: "机器学习", recommended_topic_id: topics[0].id, groups: [{ id: "stage-1", title: "机器学习基础", parent_group_id: null, order_index: 1, topics }] });
  if (endpoint.includes("/curriculum/topics/")) return json(route, topics.find((topic) => endpoint.endsWith(topic.id)) || topics[0]);
  if (endpoint.endsWith("/prerequisites")) return json(route, { topic_id: topics[0].id, owner_course: "machine_learning", can_checkpoint: true, required: [], recommended: [], related: [], unmet: [], successors: [] });
  if (endpoint.endsWith("/lesson")) return json(route, { error: { code: "CONTENT_NOT_READY", message: "No local lesson" } }, 404);
  if (endpoint.endsWith("/examples")) return json(route, { examples: [] });
  if (endpoint.endsWith("/history")) return json(route, { course: "machine_learning", events: [] });
  if (endpoint.endsWith("/chat")) return chatFailure ? json(route, { error: { code: "LLM_SERVICE_UNAVAILABLE", message: "测试服务暂不可用" } }, 502) : json(route, { answer, course: "machine_learning", sources: [] });
  if (endpoint === "/api/v1/practice/sets") {
    const value = { practice_set_id: `browser-${++serial}`, topic_id: body.topic_id, mode: body.mode, questions: Array.from({ length: body.count }, (_, index) => ({ question_id: `q${index}`, position: index + 1, question_type: "numeric", difficulty: "easy", question: `练习 ${index + 1}：六乘七是多少？`, dimension_names: ["concept"] })), source_summary: [] };
    instances.set(value.practice_set_id, value);
    return json(route, value, 201);
  }
  if (endpoint.endsWith("/submit")) {
    const value = instances.get(endpoint.split("/").at(-2));
    return json(route, { practice_set_id: value.practice_set_id, total_score: 100, mastery_before: null, mastery_after: 0.6, evaluations: value.questions.map((question) => ({ question_id: question.question_id, score: 100, verdict: "正确", feedback: "计算正确", correct_points: [], missing_points: [], misconception_tags: [], reference_answer: "42", sources: [], evaluation_reliable: true })), gate: { passed: false, next_action: "practice", requirements: {} }, status: "evaluated" });
  }
  problems.push(`Unhandled API: ${endpoint}`);
  return json(route, {}, 500);
});

const input = page.getByRole("textbox", { name: "围绕当前知识点自由提问" });
const closeTools = () => page.getByRole("button", { name: "关闭学习工具" }).click();
try {
  await page.goto(`${baseUrl}/learn/machine_learning/${topics[0].id}`);
  await input.waitFor();
  assert.equal(await page.getByRole("dialog").count(), 0);
  assert.equal(await page.getByRole("heading", { name: "学习目标", exact: true }).count(), 0);
  assert(await page.evaluate(() => document.documentElement.scrollHeight <= window.innerHeight + 1));
  await input.fill("什么是监督学习？");
  await input.press("Enter");
  await page.getByText(answer, { exact: true }).waitFor();
  assert.equal(requests.find((request) => request.endpoint.endsWith("/chat")).body.topic_id, topics[0].id);
  await page.getByRole("button", { name: "知识点资料", exact: true }).click();
  await page.getByRole("dialog", { name: "知识点资料" }).waitFor();
  await page.keyboard.press("Escape");
  await page.getByRole("dialog").waitFor({ state: "hidden" });
  await page.getByRole("button", { name: "练习与测试", exact: true }).click();
  await page.getByRole("button", { name: "AI 生成 5 道综合验收", exact: true }).click();
  await page.locator('dialog input[inputmode="decimal"]').first().waitFor();
  assert.equal(await page.locator('dialog input[inputmode="decimal"]').count(), 5);
  await closeTools();
  assert(await input.isDisabled(), "An active formal test must disable AI assistance");
  await page.getByRole("button", { name: "练习与测试", exact: true }).click();
  for (const answerInput of await page.locator('dialog input[inputmode="decimal"]').all()) await answerInput.fill("42");
  await page.getByRole("button", { name: "提交整套答案", exact: true }).click();
  await page.getByRole("region", { name: "学习结果" }).waitFor();
  await closeTools();
  assert(await input.isEnabled());
  await page.getByRole("button", { name: "新对话", exact: true }).click();
  assert.equal(await page.getByText(answer, { exact: true }).count(), 0);
  chatFailure = true;
  await input.fill("重试问题");
  await input.press("Enter");
  await page.getByRole("alert").filter({ hasText: "测试服务暂不可用" }).waitFor();
  assert.equal(await input.inputValue(), "重试问题", "Failed questions remain editable");
  chatFailure = false;
  await input.press("Enter");
  await page.getByText(answer, { exact: true }).waitFor();
  await page.getByRole("link", { name: `下一个：${topics[1].title}`, exact: true }).click();
  await page.getByRole("heading", { name: topics[1].title, exact: true }).waitFor();
  assert.equal(await page.getByText(answer, { exact: true }).count(), 0, "Topics must have independent conversations");
  const artifacts = path.resolve(".browser-artifacts"); await mkdir(artifacts, { recursive: true });
  await page.screenshot({ path: path.join(artifacts, "topic-chat-desktop.png") });
  await page.setViewportSize({ width: 390, height: 844 });
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth && document.querySelector("#topic-question").getBoundingClientRect().bottom <= innerHeight));
  await page.getByRole("button", { name: "☰ 课程目录", exact: true }).click();
  await page.getByRole("button", { name: "关闭课程目录", exact: true }).waitFor();
  await page.keyboard.press("Escape");
  await page.screenshot({ path: path.join(artifacts, "topic-chat-mobile.png") });
  assert.deepEqual(problems, []);
  process.stdout.write("PASS chat, tools, practice state, formal-test restrictions, retry, topic navigation and mobile layout. All API calls mocked.\n");
} finally { await browser.close(); }
