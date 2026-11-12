"use client";

import { redirect, useParams } from "next/navigation";

export default function PreviousTopicsPage() {
  const { courseId } = useParams<{ courseId: string }>();
  redirect(`/admin/courses/${encodeURIComponent(courseId)}`);
}
