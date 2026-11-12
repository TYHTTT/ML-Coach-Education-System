"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useStudent } from "@/components/StudentProvider";
import { emptyTopicChat, isLearningPath, loadTopicSessions, saveTopicSessions, topicChatKey, type TopicChatState } from "@/lib/topic-chat-storage";
import type { Course } from "@/lib/types";

type Update = (current: TopicChatState) => TopicChatState;
type SessionContext = {
  chats: Record<string, TopicChatState>;
  lastPath: string | null;
  storageError: boolean;
  update: (key: string, updater: Update) => void;
  begin: (key: string) => AbortController | null;
  finish: (key: string, controller: AbortController) => void;
  stop: (key: string) => void;
  rememberPath: (path: string) => void;
};
const Context = createContext<SessionContext | null>(null);

function SessionStore({ studentId, children }: { studentId: string; children: ReactNode }) {
  const [sessions, setSessions] = useState(() => loadTopicSessions(studentId));
  const [storageError, setStorageError] = useState(false);
  const controllers = useRef(new Map<string, AbortController>());
  useEffect(() => {
    const timer = window.setTimeout(() => setStorageError(!saveTopicSessions(studentId, sessions)), 0);
    return () => window.clearTimeout(timer);
  }, [studentId, sessions]);
  useEffect(() => {
    const active = controllers.current;
    return () => { for (const controller of active.values()) controller.abort(); active.clear(); };
  }, []);
  const update = useCallback((key: string, updater: Update) => {
    setSessions((current) => ({ ...current, chats: { ...current.chats, [key]: updater(current.chats[key] ?? emptyTopicChat()) } }));
  }, []);
  const begin = useCallback((key: string) => {
    if (controllers.current.has(key)) return null;
    const controller = new AbortController();
    controllers.current.set(key, controller);
    return controller;
  }, []);
  const finish = useCallback((key: string, controller: AbortController) => {
    if (controllers.current.get(key) !== controller) return;
    controllers.current.delete(key);
    update(key, (current) => ({ ...current, pending: null, pendingMessage: "" }));
  }, [update]);
  const stop = useCallback((key: string) => { controllers.current.get(key)?.abort(); }, []);
  const rememberPath = useCallback((path: string) => {
    if (isLearningPath(path)) setSessions((current) => current.lastPath === path ? current : { ...current, lastPath: path });
  }, []);
  const context = useMemo(() => ({ chats: sessions.chats, lastPath: sessions.lastPath, storageError, update, begin, finish, stop, rememberPath }), [sessions, storageError, update, begin, finish, stop, rememberPath]);
  return <Context.Provider value={context}>{children}</Context.Provider>;
}

export default function TopicSessionsProvider({ children }: { children: ReactNode }) {
  const { student } = useStudent();
  const id = student?.student_id ?? "";
  return <SessionStore key={id} studentId={id}>{children}</SessionStore>;
}
export function useTopicSessions() {
  const context = useContext(Context);
  if (!context) throw new Error("TopicSessionsProvider 未初始化");
  return context;
}
export function useTopicConversation(course: Course, topicId: string) {
  const context = useTopicSessions();
  const { update: updateSession, begin: beginSession, finish: finishSession, stop: stopSession } = context;
  const key = topicChatKey(course, topicId);
  const update = useCallback((updater: Update) => updateSession(key, updater), [updateSession, key]);
  const begin = useCallback(() => beginSession(key), [beginSession, key]);
  const finish = useCallback((controller: AbortController) => finishSession(key, controller), [finishSession, key]);
  const stop = useCallback(() => stopSession(key), [stopSession, key]);
  return { state: context.chats[key] ?? emptyTopicChat(), update, begin, finish, stop, rememberPath: context.rememberPath, storageError: context.storageError };
}
