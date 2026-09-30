'use client';

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';

type AppShellContextValue = {
  /** Command palette open state, lifted so chrome (search button) can open it (F2). */
  commandPaletteOpen: boolean;
  openCommandPalette: () => void;
  closeCommandPalette: () => void;
};

const AppShellContext = createContext<AppShellContextValue | null>(null);

export function AppShellProvider({ children }: { children: ReactNode }) {
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const openCommandPalette = useCallback(() => setCommandPaletteOpen(true), []);
  const closeCommandPalette = useCallback(() => setCommandPaletteOpen(false), []);

  const value = useMemo(
    () => ({ commandPaletteOpen, openCommandPalette, closeCommandPalette }),
    [commandPaletteOpen, openCommandPalette, closeCommandPalette]
  );

  return <AppShellContext.Provider value={value}>{children}</AppShellContext.Provider>;
}

export function useAppShell(): AppShellContextValue {
  const ctx = useContext(AppShellContext);
  if (!ctx) {
    throw new Error('useAppShell must be used within AppShellProvider');
  }
  return ctx;
}
