// Treat explicit reference sections as separate content, without enabling raw HTML.
function maskCode(content: string): string {
  let fence: { character: string; length: number } | null = null;
  return content.split("\n").map((line) => {
    const delimiter = /^ {0,3}(`{3,}|~{3,})/.exec(line)?.[1];
    if (fence) {
      if (delimiter?.[0] === fence.character && delimiter.length >= fence.length && line.trim() === delimiter) fence = null;
      return line.replace(/[^\r\n]/g, " ");
    }
    if (delimiter) {
      fence = { character: delimiter[0], length: delimiter.length };
      return line.replace(/[^\r\n]/g, " ");
    }
    return line.replace(/(`+)[^\n]*?\1/g, (code) => " ".repeat(code.length));
  }).join("\n");
}

export function splitPracticeContent(content: string): { question: string; reference: string } {
  const references: string[] = [];
  const visible: string[] = [];
  let depth = 0;
  let start = 0;
  let cursor = 0;
  for (const tag of maskCode(content).matchAll(/<\/?details\b[^>]*>/gi)) {
    const closing = /^<\//.test(tag[0]);
    if (!closing) {
      if (depth === 0) { visible.push(content.slice(cursor, tag.index)); start = tag.index; }
      depth++;
    } else if (depth > 0 && --depth === 0) {
      cursor = tag.index + tag[0].length;
      references.push(content.slice(start, cursor));
    }
  }
  if (depth) references.push(content.slice(start));
  else visible.push(content.slice(cursor));
  let question = visible.join("\n\n");
  const referenceHeading = /^ {0,3}(?:#{1,6}\s*)?(?:\*\*|__)?(?:\d+[.)、]\s*)?(?:参考(?:答案|思路|解析)|标准答案|正确答案|答案|解答|解析|解题思路|answer(?: key)?|solution|explanation)(?:与解析|及解析)?(?:\*\*|__)?[ \t]*(?:[:：].*|#*[ \t]*)$/im;
  const heading = referenceHeading.exec(maskCode(question));
  if (heading) {
    references.push(question.slice(heading.index));
    question = question.slice(0, heading.index);
  }
  return {
    question: question.trim(),
    reference: references.map((section) => section
      .replace(/<summary\b[^>]*>[\s\S]*?<\/summary\s*>/gi, "")
      .replace(/<\/?details\b[^>]*>/gi, "")
      .trim()).filter(Boolean).join("\n\n"),
  };
}
