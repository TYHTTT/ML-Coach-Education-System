import assert from "node:assert/strict";
import { test } from "node:test";
import { splitPracticeContent } from "../lib/practice-content.ts";

test("separates Dify details references and preserves later questions", () => {
  const result = splitPracticeContent(
    "问题一：什么是标签？\n\n<details open><summary>参考思路</summary>标签是目标结果。</details>\n\n问题二：举一个例子。\n<details><summary>参考答案</summary>房屋价格。</details>",
  );
  assert.match(result.question, /问题一/);
  assert.match(result.question, /问题二/);
  assert.doesNotMatch(result.question, /目标结果|房屋价格|details|summary/);
  assert.match(result.reference, /标签是目标结果/);
  assert.match(result.reference, /房屋价格/);
  assert.doesNotMatch(result.reference, /<\/?(?:details|summary)/);
});

test("nested or unfinished details never spill their reference into questions", () => {
  for (const content of [
    "题目正文\n<details><summary>参考</summary>隐藏答案<details>隐藏步骤</details></details>\n补充题目",
    "题目正文\n<details><summary>参考</summary>隐藏答案",
  ]) {
    const result = splitPracticeContent(content);
    assert.match(result.question, /题目正文/);
    assert.doesNotMatch(result.question, /隐藏/);
    assert.match(result.reference, /隐藏答案/);
  }
});

test("recognizes common Markdown reference section headings", () => {
  for (const heading of [
    "## 参考答案",
    "**参考思路：**",
    "### 答案与解析",
    "解析：",
    "### Solution",
    "**1. 标准答案**",
  ]) {
    const result = splitPracticeContent(`题目正文\n\n${heading}\n隐藏答案`);
    assert.equal(result.question, "题目正文", heading);
    assert.match(result.reference, /隐藏答案/, heading);
  }
});

test("keeps code examples and question wording intact", () => {
  const question =
    "请分析以下代码，答案是否唯一？\n\n```html\n<details><summary>演示标签</summary>代码内容</details>\n## 参考答案\n```\n\n说明 `<details>` 标签的用途。";
  assert.deepEqual(splitPracticeContent(question), { question, reference: "" });
});

test("does not turn an answer-only response into a visible question", () => {
  assert.equal(
    splitPracticeContent("<details><summary>参考</summary>答案内容</details>")
      .question,
    "",
  );
  assert.equal(splitPracticeContent("## 参考答案\n答案内容").question, "");
});
