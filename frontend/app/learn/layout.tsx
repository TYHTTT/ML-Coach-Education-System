import type { Metadata } from "next";
import LearningShell from "@/components/LearningShell";
import CourseLayout from "@/components/CourseLayout";
import CourseCatalogProvider from "@/components/CourseCatalogProvider";
import { Suspense } from "react";

export const metadata: Metadata = {
  title: "课程学习",
  description: "围绕知识点讲解、练习、评价与掌握度更新的学习闭环",
};

export default function LearnLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <LearningShell><CourseCatalogProvider><Suspense fallback={<div className="p-8" role="status">正在准备课程目录…</div>}><CourseLayout>{children}</CourseLayout></Suspense></CourseCatalogProvider></LearningShell>;
}
