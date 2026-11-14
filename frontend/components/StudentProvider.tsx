"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { isStudentNotFound, logoutStudent } from "@/lib/api";
import type { AuthenticatedStudent } from "@/lib/types";

export const STUDENT_STORAGE_KEY = "course_coach_access_token";
export const STUDENT_PROFILE_STORAGE_KEY = "course_coach_student_profile";

type StudentStatus = "initializing" | "ready" | "unauthenticated" | "error";

interface StudentContextValue {
  studentId: string | null;
  student: Pick<
    AuthenticatedStudent,
    "student_id" | "username" | "display_name"
  > | null;
  status: StudentStatus;
  error: string | null;
  withStudent: <T>(request: (studentId: string) => Promise<T>) => Promise<T>;
  completeLogin: (student: AuthenticatedStudent) => void;
  logout: () => Promise<void>;
}

const StudentContext = createContext<StudentContextValue | null>(null);

export function StudentProvider({ children }: { children: ReactNode }) {
  const [studentId, setStudentId] = useState<string | null>(null);
  const [student, setStudent] = useState<StudentContextValue["student"]>(null);
  const [status, setStatus] = useState<StudentStatus>("initializing");
  const [error, setError] = useState<string | null>(null);
  const studentIdRef = useRef<string | null>(null);

  const rememberStudent = useCallback((id: string | null) => {
    studentIdRef.current = id;
    setStudentId(id);
  }, []);

  const clearSession = useCallback(() => {
    studentIdRef.current = null;
    setStudentId(null);
    setStudent(null);
    try {
      window.localStorage.removeItem(STUDENT_STORAGE_KEY);
      window.localStorage.removeItem(STUDENT_PROFILE_STORAGE_KEY);
    } catch {
      /* The UI still clears its in-memory session. */
    }
  }, []);

  const initialize = useCallback(async () => {
    setStatus("initializing");
    setError(null);
    try {
      let storedToken: string | null = null;
      let storedProfile: StudentContextValue["student"] = null;
      try {
        storedToken = window.localStorage.getItem(STUDENT_STORAGE_KEY);
        const rawProfile = window.localStorage.getItem(
          STUDENT_PROFILE_STORAGE_KEY,
        );
        storedProfile = rawProfile ? JSON.parse(rawProfile) : null;
      } catch {
        // Storage is optional; the user can still sign in for this session.
      }
      if (!storedToken?.trim() || !storedProfile?.student_id) {
        clearSession();
        setStatus("unauthenticated");
        return;
      }
      rememberStudent(storedToken);
      setStudent(storedProfile);
      setStatus("ready");
    } catch (cause) {
      clearSession();
      setStatus("error");
      setError(
        cause instanceof Error
          ? cause.message
          : "登录状态恢复失败，请重新登录。",
      );
    }
  }, [clearSession, rememberStudent]);

  useEffect(() => {
    const timer = window.setTimeout(() => void initialize(), 0);
    return () => window.clearTimeout(timer);
  }, [initialize]);

  const ensureStudent = useCallback(async (): Promise<string> => {
    const current = studentIdRef.current;
    if (current) return current;
    throw new Error("请先登录后再继续学习。");
  }, []);

  const withStudent = useCallback(
    async <T,>(request: (id: string) => Promise<T>): Promise<T> => {
      const id = await ensureStudent();
      try {
        return await request(id);
      } catch (cause) {
        if (!isStudentNotFound(cause)) throw cause;

        clearSession();
        setStatus("unauthenticated");
        throw new Error("登录已过期，请重新登录。");
      }
    },
    [clearSession, ensureStudent],
  );

  const completeLogin = useCallback(
    (authenticated: AuthenticatedStudent) => {
      const profile = {
        student_id: authenticated.student_id,
        username: authenticated.username,
        display_name: authenticated.display_name,
      };
      rememberStudent(authenticated.access_token);
      setStudent(profile);
      try {
        window.localStorage.setItem(
          STUDENT_STORAGE_KEY,
          authenticated.access_token,
        );
        window.localStorage.setItem(
          STUDENT_PROFILE_STORAGE_KEY,
          JSON.stringify(profile),
        );
      } catch {
        /* Keep the active session in memory when storage is unavailable. */
      }
      setError(null);
      setStatus("ready");
    },
    [rememberStudent],
  );

  const logout = useCallback(async () => {
    const token = studentIdRef.current;
    if (token) {
      try {
        await logoutStudent(token);
      } catch {
        /* Local logout remains valid if the server is unavailable. */
      }
    }
    clearSession();
    setStatus("unauthenticated");
  }, [clearSession]);

  const value = useMemo<StudentContextValue>(
    () => ({
      studentId,
      student,
      status,
      error,
      withStudent,
      completeLogin,
      logout,
    }),
    [completeLogin, error, logout, status, student, studentId, withStudent],
  );

  return (
    <StudentContext.Provider value={value}>{children}</StudentContext.Provider>
  );
}

export function useStudent(): StudentContextValue {
  const context = useContext(StudentContext);
  if (!context) throw new Error("useStudent 必须在 StudentProvider 内使用。");
  return context;
}
