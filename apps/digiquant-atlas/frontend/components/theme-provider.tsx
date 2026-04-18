'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

/** User preference: fixed light/dark, or follow OS */
export type AtlasTheme = 'light' | 'dark' | 'auto';

const STORAGE_KEY = 'atlas-theme';

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
  const [theme, setThemeState] = useState<AtlasTheme>('auto');
  const [effectiveTheme, setEffectiveTheme] = useState<'light' | 'dark'>('dark');

  useLayoutEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      const t: AtlasTheme =
        raw === 'light' || raw === 'dark' || raw === 'auto'
          ? raw
          : 'auto';
      // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate from localStorage
      setThemeState(t);
      const eff = resolveEffectiveTheme(t);
      setEffectiveTheme(eff);
      applyHtmlColorScheme(t);
    } catch {
      applyHtmlColorScheme('auto');
      setEffectiveTheme(resolveEffectiveTheme('auto'));
    }
  }, []);

  useEffect(() => {
    if (theme !== 'auto') return;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => {
      const eff = resolveEffectiveTheme('auto');
      setEffectiveTheme(eff);
      applyHtmlColorScheme('auto');
    };
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, [theme]);

  const setTheme = useCallback((t: AtlasTheme) => {
    try {
      localStorage.setItem(STORAGE_KEY, t);
    } catch {
      /* ignore */
    }
    setThemeState(t);
    const eff = resolveEffectiveTheme(t);
    setEffectiveTheme(eff);
    applyHtmlColorScheme(t);
  }, []);

  const value = useMemo(
    () => ({ theme, effectiveTheme, setTheme }),
    [theme, effectiveTheme, setTheme]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
