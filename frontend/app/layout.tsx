import type { Metadata, Viewport } from "next";
import { StudentProvider } from "@/components/StudentProvider";
import AuthGate from "@/components/AuthGate";
import { ThemeProvider } from "@/components/ThemeProvider";
import "katex/dist/katex.min.css";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Course Coach · 课程问答助手",
    template: "%s · Course Coach",
  },
  description: "由 Dify Agent 提供支持的中文课程辅导助手",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#f6f8fc",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <ThemeProvider>
          <StudentProvider><AuthGate>{children}</AuthGate></StudentProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
