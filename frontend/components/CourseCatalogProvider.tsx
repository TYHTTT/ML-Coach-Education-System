"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { getCourses } from "@/lib/api";
import type { CourseRecord } from "@/lib/types";

interface Catalog {
  courses: CourseRecord[];
  loading: boolean;
  error: string;
  reload: () => void;
}
const Context = createContext<Catalog | null>(null);

export default function CourseCatalogProvider({
  children,
}: {
  children: ReactNode;
}) {
  const [courses, setCourses] = useState<CourseRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  const reload = useCallback(() => {
    setVersion((current) => current + 1);
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setLoading(true);
      setError("");
      try {
        const value = await getCourses(controller.signal);
        if (!controller.signal.aborted) setCourses(value);
      } catch (cause) {
        if (!controller.signal.aborted)
          setError(
            cause instanceof Error ? cause.message : "课程列表加载失败。",
          );
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, 0);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [version]);
  const value = useMemo(
    () => ({ courses, loading, error, reload }),
    [courses, loading, error, reload],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useCourseCatalog() {
  const context = useContext(Context);
  if (!context) throw new Error("CourseCatalogProvider 未初始化");
  return context;
}
