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

const start = page.getByRole("button", { name: "开始学习", exact: true });
const closeTools = () => page.getByRole("button", { name: "关闭学习工具" }).click();
try {
  await page.goto(`${baseUrl}/learn/machine_learning/${topics[0].id}`);
  await start.waitFor();
  assert.equal(requests.filter((request) => request.endpoint.endsWith("/chat")).length, 0, "Opening a topic must not generate a lesson automatically");
  assert.equal(await page.locator("#topic-tutor textarea, #topic-tutor form").count(), 0);
  assert.equal(await page.getByRole("dialog").count(), 0);
  assert(await page.evaluate(() => document.documentElement.scrollHeight <= innerHeight + 1));
  await start.click();
  await page.getByRole("article", { name: "知识点讲解" }).waitFor();
  await page.getByText(answer, { exact: true }).waitFor();
  const request = requests.find((request) => request.endpoint.endsWith("/chat"));
  assert.equal(request.body.topic_id, topics[0].id);
  assert.equal(request.body.learning_mode, "topic_teaching");
  assert.equal(request.body.message, `当前课程是机器学习，我要开始学习${topics[0].title}`);
  assert.deepEqual(request.body.history, []);
  assert.equal(await page.getByRole("article", { name: "你的消息" }).count(), 0);
  await page.getByRole("button", { name: "没看懂", exact: true }).click();
  const questionDialog = page.getByRole("dialog", { name: "哪里没看懂？" });
  await questionDialog.waitFor();
  await questionDialog.getByRole("textbox").fill("标签是什么意思？");
  chatFailure = true;
  await questionDialog.getByRole("button", { name: "继续讲解", exact: true }).click();
  await questionDialog.getByRole("alert").waitFor();
  assert.equal(await questionDialog.getByRole("textbox").inputValue(), "标签是什么意思？");
  chatFailure = false;
  await questionDialog.getByRole("button", { name: "继续讲解", exact: true }).click();
  await page.getByRole("article", { name: "补充讲解" }).waitFor();
  await questionDialog.waitFor({ state: "hidden" });
  const clarification = requests.filter((item) => item.endpoint.endsWith("/chat")).at(-1).body;
  assert.equal(clarification.learning_mode, "topic_clarification");
  assert.equal(clarification.message, "我没看懂：标签是什么意思？");
  assert.deepEqual(clarification.history, [{ role: "user", content: `当前课程是机器学习，我要开始学习${topics[0].title}` }, { role: "assistant", content: answer }]);
  await page.getByRole("button", { name: "做练习", exact: true }).click();
  const exerciseDialog = page.getByRole("dialog", { name: "练习与测试" });
  await exerciseDialog.locator('input[inputmode="decimal"]').first().waitFor();
  assert.equal(await exerciseDialog.locator('input[inputmode="decimal"]').count(), 3);
  assert.equal(serial, 1, "The practice branch generates exactly one set automatically");
  await exerciseDialog.locator('input[inputmode="decimal"]').first().fill("42");
  await closeTools();
  await page.getByRole("button", { name: "做练习", exact: true }).click();
  assert.equal(await exerciseDialog.locator('input[inputmode="decimal"]').first().inputValue(), "42");
  assert.equal(serial, 1, "Reopening unfinished practice must preserve its answers");
  for (const input of await exerciseDialog.locator('input[inputmode="decimal"]').all()) await input.fill("42");
  await exerciseDialog.getByRole("button", { name: "提交整套答案", exact: true }).click();
  await page.getByRole("region", { name: "学习结果" }).waitFor();
  await closeTools();
  await page.getByRole("button", { name: "知识点资料", exact: true }).click();
  await page.getByRole("dialog", { name: "知识点资料" }).waitFor();
  await page.keyboard.press("Escape");
  await page.getByRole("dialog").waitFor({ state: "hidden" });
  assert.equal(await page.getByText(answer, { exact: true }).count(), 2, "Opening tools must preserve the lecture and clarification");
  await page.getByRole("link", { name: `下一个：${topics[1].title}`, exact: true }).click();
  await page.getByRole("heading", { name: topics[1].title, exact: true }).waitFor();
  await start.waitFor();
  assert.equal(await page.getByText(answer, { exact: true }).count(), 0, "Topics must have independent lectures");
  await page.getByRole("button", { name: "练习与测试", exact: true }).click();
  await page.getByRole("button", { name: "AI 生成 5 道综合验收", exact: true }).click();
  await page.locator('dialog input[inputmode="decimal"]').first().waitFor();
  assert.equal(await page.locator('dialog input[inputmode="decimal"]').count(), 5);
  await closeTools();
  assert(await start.isDisabled(), "An active formal test must disable lesson generation");
  await page.getByRole("button", { name: "练习与测试", exact: true }).click();
  for (const answerInput of await page.locator('dialog input[inputmode="decimal"]').all()) await answerInput.fill("42");
  await page.getByRole("button", { name: "提交整套答案", exact: true }).click();
  await page.getByRole("region", { name: "学习结果" }).waitFor();
  await closeTools();
  assert(await start.isEnabled());
  chatFailure = true;
  await start.click();
  await page.getByRole("alert").filter({ hasText: "测试服务暂不可用" }).waitFor();
  assert.equal(await page.getByRole("article", { name: "知识点讲解" }).count(), 0);
  chatFailure = false;
  await start.click();
  await page.getByText(answer, { exact: true }).waitFor();
  assert.equal(requests.filter((request) => request.endpoint.endsWith("/chat")).at(-1).body.topic_id, topics[1].id);
  const artifacts = path.resolve(".browser-artifacts"); await mkdir(artifacts, { recursive: true });
  await page.screenshot({ path: path.join(artifacts, "topic-learning-desktop.png") });
  await page.setViewportSize({ width: 390, height: 844 });
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  assert.equal(await page.locator("#topic-tutor textarea:visible").count(), 0);
  await page.getByRole("button", { name: "没看懂", exact: true }).click();
  await questionDialog.waitFor();
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await questionDialog.getByRole("button", { name: "取消", exact: true }).click();
  await page.getByRole("button", { name: "☰ 课程目录", exact: true }).click();
  await page.getByRole("button", { name: "关闭课程目录", exact: true }).waitFor();
  await page.keyboard.press("Escape");
  await page.screenshot({ path: path.join(artifacts, "topic-learning-mobile.png") });
  assert.deepEqual(problems, []);
  process.stdout.write("PASS lecture branches, contextual clarification, retry, automatic practice, answer preservation, grading, topic scope, formal-test restrictions and mobile layout. All API calls mocked.\n");
} finally { await browser.close(); }
