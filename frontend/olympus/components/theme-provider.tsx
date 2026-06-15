'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from 'react';

/** User preference: fixed light/dark, or follow OS */
export type AtlasTheme = 'light' | 'dark' | 'auto';

const STORAGE_KEY = 'olympus-theme';
/** Shared with the marketing sites (digiquant.io / digithings.ai) so the
 *  chosen theme follows the user across the same origin. Stores only 'light'|'dark'. */
const MIRROR_KEY = 'dt-theme';

export function resolveEffectiveTheme(preference: AtlasTheme): 'light' | 'dark' {
  if (preference === 'light') return 'light';
  if (preference === 'dark') return 'dark';
  if (typeof window === 'undefined') return 'dark';
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function applyHtmlColorScheme(preference: AtlasTheme) {
  if (typeof document === 'undefined') return;
  const resolved = resolveEffectiveTheme(preference);
  const root = document.documentElement;
  root.classList.remove('light', 'dark');
  root.classList.add(resolved);
}

function readStoredTheme(): AtlasTheme {
  if (typeof window === 'undefined') return 'auto';
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === 'light' || raw === 'dark' || raw === 'auto') return raw;
    // fall back to the marketing-site preference if set on this origin
    const mirror = localStorage.getItem(MIRROR_KEY);
    return mirror === 'light' || mirror === 'dark' ? mirror : 'auto';
  } catch {
    return 'auto';
  }
}

let themeEpoch = 0;
const themeListeners = new Set<() => void>();

function subscribeTheme(onStoreChange: () => void) {
  themeListeners.add(onStoreChange);
  const onStorage = (e: StorageEvent) => {
    if (e.key === STORAGE_KEY || e.key === MIRROR_KEY) onStoreChange();
  };
  window.addEventListener('storage', onStorage);
  return () => {
    themeListeners.delete(onStoreChange);
    window.removeEventListener('storage', onStorage);
  };
}

function getThemeSnapshot(): AtlasTheme {
  void themeEpoch;
  return readStoredTheme();
}

function notifyThemeSubscribers() {
  themeEpoch += 1;
  themeListeners.forEach((l) => l());
}

const ThemeContext = createContext<{
  theme: AtlasTheme;
  /** Resolved light/dark for the current preference (OS when auto) */
  effectiveTheme: 'light' | 'dark';
  setTheme: (t: AtlasTheme) => void;
} | null>(null);

export function useAtlasTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useAtlasTheme must be used within ThemeProvider');
  return ctx;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const theme = useSyncExternalStore(subscribeTheme, getThemeSnapshot, () => 'auto' as AtlasTheme);
  const effectiveTheme = resolveEffectiveTheme(theme);

  useLayoutEffect(() => {
    applyHtmlColorScheme(theme);
  }, [theme]);

  useEffect(() => {
    if (theme !== 'auto') return;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => notifyThemeSubscribers();
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, [theme]);

  const setTheme = useCallback((t: AtlasTheme) => {
    try {
      localStorage.setItem(STORAGE_KEY, t);
      // mirror the resolved light/dark so the marketing sites stay in sync
      localStorage.setItem(MIRROR_KEY, resolveEffectiveTheme(t));
    } catch {
      /* ignore */
    }
    notifyThemeSubscribers();
  }, []);

  const value = useMemo(
    () => ({ theme, effectiveTheme, setTheme }),
    [theme, effectiveTheme, setTheme]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
