'use client';

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

const COLLAPSED_KEY = 'dashboard-sidebar-collapsed';
/** Pre-rebrand key. Read once so a collapsed sidebar survives the rename; removed on first toggle. */
const LEGACY_COLLAPSED_KEY = 'research-sidebar-collapsed';
const DEFAULT_KEY = 'dashboard-sidebar-default';
const GROUPS_KEY = 'dashboard-sidebar-groups';
const STATUS_KEY = 'dashboard-sidebar-status';
const DENSITY_KEY = 'dashboard-density';

export type Density = 'compact' | 'comfortable';
export type SidebarDefault = 'expanded' | 'collapsed';

type AppShellContextValue = {
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  /** Initial state when no explicit collapse choice is stored. */
  sidebarDefault: SidebarDefault;
  setSidebarDefault: (v: SidebarDefault) => void;
  /** Drawer open state for the mobile navigation sheet (< md). */
  mobileNavOpen: boolean;
  setMobileNavOpen: (open: boolean) => void;
  /** Group ids the visitor expanded by hand (the active route's group is always open). */
  openGroups: readonly string[];
  toggleGroup: (id: string) => void;
  statusOpen: boolean;
  toggleStatus: () => void;
  density: Density;
  setDensity: (d: Density) => void;
  /** Command palette open state, lifted so chrome (search button) can open it. */
  commandPaletteOpen: boolean;
  openCommandPalette: () => void;
  closeCommandPalette: () => void;
};

const AppShellContext = createContext<AppShellContextValue | null>(null);

function read(key: string): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* storage unavailable — the preference just doesn't persist */
  }
}

function readDefault(): SidebarDefault {
  return read(DEFAULT_KEY) === 'collapsed' ? 'collapsed' : 'expanded';
}

function readCollapsed(): boolean {
  const current = read(COLLAPSED_KEY);
  if (current === '1' || current === '0') return current === '1';
  if (read(LEGACY_COLLAPSED_KEY) === '1') return true;
  return readDefault() === 'collapsed';
}

function readGroups(): string[] {
  try {
    const parsed: unknown = JSON.parse(read(GROUPS_KEY) ?? '[]');
    return Array.isArray(parsed) ? parsed.filter((g): g is string => typeof g === 'string') : [];
  } catch {
    return [];
  }
}

export function AppShellProvider({ children }: { children: ReactNode }) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(readCollapsed);
  const [sidebarDefault, setSidebarDefaultState] = useState<SidebarDefault>(readDefault);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [openGroups, setOpenGroups] = useState<string[]>(readGroups);
  const [statusOpen, setStatusOpen] = useState(() => read(STATUS_KEY) !== '0');
  const [density, setDensityState] = useState<Density>(() =>
    read(DENSITY_KEY) === 'comfortable' ? 'comfortable' : 'compact'
  );
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const openCommandPalette = useCallback(() => setCommandPaletteOpen(true), []);
  const closeCommandPalette = useCallback(() => setCommandPaletteOpen(false), []);

  const toggleSidebar = useCallback(() => {
    setSidebarCollapsed((c) => {
      const next = !c;
      write(COLLAPSED_KEY, next ? '1' : '0');
      write(LEGACY_COLLAPSED_KEY, null);
      return next;
    });
  }, []);

  const setSidebarDefault = useCallback((v: SidebarDefault) => {
    setSidebarDefaultState(v);
    write(DEFAULT_KEY, v);
  }, []);

  const toggleGroup = useCallback((id: string) => {
    setOpenGroups((g) => {
      const next = g.includes(id) ? g.filter((x) => x !== id) : [...g, id];
      write(GROUPS_KEY, JSON.stringify(next));
      return next;
    });
  }, []);

  const toggleStatus = useCallback(() => {
    setStatusOpen((s) => {
      write(STATUS_KEY, s ? '0' : '1');
      return !s;
    });
  }, []);

  const setDensity = useCallback((d: Density) => {
    setDensityState(d);
    write(DENSITY_KEY, d);
  }, []);

  const value = useMemo(
    () => ({
      sidebarCollapsed,
      toggleSidebar,
      sidebarDefault,
      setSidebarDefault,
      mobileNavOpen,
      setMobileNavOpen,
      openGroups,
      toggleGroup,
      statusOpen,
      toggleStatus,
      density,
      setDensity,
      commandPaletteOpen,
      openCommandPalette,
      closeCommandPalette,
    }),
    [
      sidebarCollapsed,
      toggleSidebar,
      sidebarDefault,
      setSidebarDefault,
      mobileNavOpen,
      openGroups,
      toggleGroup,
      statusOpen,
      toggleStatus,
      density,
      setDensity,
      commandPaletteOpen,
      openCommandPalette,
      closeCommandPalette,
    ]
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
