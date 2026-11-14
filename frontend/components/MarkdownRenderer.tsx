"use client";

import { useState, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { CheckIcon, CopyIcon } from "@/components/Icons";

function CodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false);

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="code-shell not-prose my-5 overflow-hidden rounded-2xl border border-slate-700 bg-[#282c34] shadow-sm">
      <div className="flex items-center justify-between border-b border-white/10 bg-black/20 px-4 py-2">
        <span className="font-mono text-[11px] font-medium uppercase tracking-wider text-slate-300">
          {language || "text"}
        </span>
        <button
          type="button"
          onClick={copyCode}
          className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-slate-300 transition hover:bg-white/10 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
          aria-label="复制代码"
        >
          {copied ? (
            <CheckIcon className="size-3.5" />
          ) : (
            <CopyIcon className="size-3.5" />
          )}
          {copied ? "已复制" : "复制"}
        </button>
      </div>
      <SyntaxHighlighter
        language={language || "text"}
        style={oneDark}
        customStyle={{
          margin: 0,
          padding: "1rem",
          background: "#282c34",
          fontSize: "0.82rem",
          lineHeight: 1.65,
        }}
        codeTagProps={{ style: { fontFamily: "var(--font-mono)" } }}
        wrapLongLines
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}

function textFromChildren(children: ReactNode): string {
  return String(children).replace(/\n$/, "");
}

const components: Components = {
  pre: ({ children }) => <>{children}</>,
  code: ({ className, children, ...props }) => {
    const match = /language-([\w-]+)/.exec(className ?? "");
    const code = textFromChildren(children);
    if (match || code.includes("\n")) {
      return <CodeBlock language={match?.[1] ?? "text"} code={code} />;
    }
    return (
      <code
        className="rounded-md bg-slate-100 px-1.5 py-0.5 font-mono text-[0.88em] font-medium text-indigo-700"
        {...props}
      >
        {children}
      </code>
    );
  },
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
  table: ({ children }) => (
    <div className="my-5 overflow-x-auto rounded-xl border border-slate-200">
      <table className="my-0 min-w-full">{children}</table>
    </div>
  ),
};

function safeUrl(url: string): string {
  const normalized = url.trim().toLowerCase();
  if (
    normalized.startsWith("http://") ||
    normalized.startsWith("https://") ||
    normalized.startsWith("mailto:") ||
    normalized.startsWith("/") ||
    normalized.startsWith("#")
  ) {
    return url;
  }
  return "";
}

export default function MarkdownRenderer({ content }: { content: string }) {
  return (
    <div className="prose prose-slate max-w-none text-[15px] leading-7 prose-headings:scroll-mt-20 prose-headings:font-semibold prose-headings:text-slate-900 prose-h1:text-xl prose-h2:mt-7 prose-h2:text-lg prose-h3:text-base prose-p:my-3 prose-a:text-indigo-600 prose-a:no-underline hover:prose-a:underline prose-li:my-1 prose-strong:text-slate-900 prose-th:bg-slate-50 prose-th:px-3 prose-th:py-2 prose-td:px-3 prose-td:py-2">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={components}
        urlTransform={safeUrl}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
