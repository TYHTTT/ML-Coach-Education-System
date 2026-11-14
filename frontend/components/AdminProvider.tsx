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
import { ApiError, getCurrentAdmin, logoutAdmin } from "@/lib/api";
import type { Administrator, AuthenticatedAdmin } from "@/lib/types";

const STORAGE_KEY = "course_coach_admin_access_token";
type Status = "initializing" | "ready" | "unauthenticated" | "error";
interface AdminContextValue {
  admin: Administrator | null;
  status: Status;
  error: string;
  completeLogin: (account: AuthenticatedAdmin) => void;
  logout: () => Promise<void>;
  retry: () => void;
  withAdmin: <T>(action: (token: string) => Promise<T>) => Promise<T>;
}
const Context = createContext<AdminContextValue | null>(null);

export function AdminProvider({ children }: { children: ReactNode }) {
  const [admin, setAdmin] = useState<Administrator | null>(null);
  const [status, setStatus] = useState<Status>("initializing");
  const [error, setError] = useState("");
  const tokenRef = useRef<string | null>(null);

  const clear = useCallback(() => {
    tokenRef.current = null;
    setAdmin(null);
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* Session still clears in memory. */
    }
    setStatus("unauthenticated");
  }, []);

  const restore = useCallback(
    async (signal?: AbortSignal) => {
      setStatus("initializing");
      setError("");
      try {
        let token = tokenRef.current;
        try {
          token ??= window.localStorage.getItem(STORAGE_KEY);
        } catch {
          /* Browser storage is optional. */
        }
        if (!token) {
          clear();
          return;
        }
        const profile = await getCurrentAdmin(token, signal);
        if (signal?.aborted) return;
        tokenRef.current = token;
        setAdmin(profile);
        setStatus("ready");
      } catch (cause) {
        if (signal?.aborted) return;
        if (cause instanceof ApiError && cause.status === 401) {
          clear();
          setError("管理员登录已过期，请重新登录。");
        } else {
          setError(
            cause instanceof Error
              ? cause.message
              : "暂时无法验证管理员登录状态。",
          );
          setStatus("error");
        }
      }
    },
    [clear],
  );

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => void restore(controller.signal), 0);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [restore]);

  const completeLogin = useCallback((account: AuthenticatedAdmin) => {
    const { access_token: token, ...profile } = account;
    tokenRef.current = token;
    setAdmin(profile);
    try {
      window.localStorage.setItem(STORAGE_KEY, token);
    } catch {
      /* Keep this session available in memory. */
    }
    setError("");
    setStatus("ready");
  }, []);

  const logout = useCallback(async () => {
    try {
      if (tokenRef.current) await logoutAdmin(tokenRef.current);
    } finally {
      clear();
    }
  }, [clear]);
  const retry = useCallback(() => {
    void restore();
  }, [restore]);
  const withAdmin = useCallback(
    async <T,>(action: (token: string) => Promise<T>) => {
      const token = tokenRef.current;
      if (!token) throw new Error("请先登录管理员账户。");
      try {
        return await action(token);
      } catch (cause) {
        if (cause instanceof ApiError && cause.status === 401) {
          clear();
          setError("管理员登录已过期，请重新登录。");
        }
        throw cause;
      }
    },
    [clear],
  );
  const value = useMemo(
    () => ({ admin, status, error, completeLogin, logout, retry, withAdmin }),
    [admin, status, error, completeLogin, logout, retry, withAdmin],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useAdmin() {
  const context = useContext(Context);
  if (!context) throw new Error("AdminProvider 未初始化");
  return context;
}
