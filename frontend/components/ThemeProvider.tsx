"use client";

import {
  createContext,
  useContext,
  useEffect,
  useSyncExternalStore,
  type ReactNode,
} from "react";

type Theme = "light" | "dark";

interface ThemeContextValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);
const THEME_STORAGE_KEY = "course-coach-theme";
let fallbackTheme: Theme = "light";
let memoryOnly = false;
const themeListeners = new Set<() => void>();

function storedTheme(value: string | null): Theme {
  return value === "dark" ? "dark" : "light";
}

function getThemeSnapshot(): Theme {
  if (memoryOnly) return fallbackTheme;
  try { return storedTheme(window.localStorage.getItem(THEME_STORAGE_KEY)); }
  catch { return fallbackTheme; }
}

function getServerThemeSnapshot(): Theme { return "light"; }

function subscribeToTheme(listener: () => void) {
  themeListeners.add(listener);
  function onStorage(event: StorageEvent) {
    if (event.key !== THEME_STORAGE_KEY && event.key !== null) return;
    if (event.storageArea) {
      try { if (event.storageArea !== window.localStorage) return; }
      catch { return; }
    }
    fallbackTheme = storedTheme(event.newValue);
    memoryOnly = false;
    listener();
  }
  window.addEventListener("storage", onStorage);
  return () => {
    themeListeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

function updateTheme(nextTheme: Theme) {
  fallbackTheme = nextTheme;
  try { window.localStorage.setItem(THEME_STORAGE_KEY, nextTheme); memoryOnly = false; }
  catch { memoryOnly = true; }
  for (const listener of themeListeners) listener();
}

function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const theme = useSyncExternalStore(subscribeToTheme, getThemeSnapshot, getServerThemeSnapshot);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  return (
    <ThemeContext.Provider value={{ theme, setTheme: updateTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("useTheme must be used within ThemeProvider");
  return context;
}
