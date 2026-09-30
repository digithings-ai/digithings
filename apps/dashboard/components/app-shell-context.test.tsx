/**
 * @vitest-environment happy-dom
 */
import { createElement, useEffect } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { act } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AppShellProvider, useAppShell } from './app-shell-context';

type Shell = ReturnType<typeof useAppShell>;

function Probe({ onReady }: { onReady: (shell: Shell) => void }) {
  const shell = useAppShell();
  useEffect(() => {
    onReady(shell);
  }, [onReady, shell]);
  return null;
}

describe('AppShellProvider', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  function mount() {
    let latest: Shell | null = null;
    act(() => {
      root.render(
        createElement(
          AppShellProvider,
          null,
          createElement(Probe, {
            onReady: (shell) => {
              latest = shell;
            },
          })
        )
      );
    });
    return () => latest!;
  }

  beforeEach(() => {
    const store = new Map<string, string>();
    vi.stubGlobal('localStorage', {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
      clear: () => store.clear(),
    });
  });

  it('opens and closes the command palette', () => {
    const shell = mount();
    expect(shell().commandPaletteOpen).toBe(false);
    act(() => shell().openCommandPalette());
    expect(shell().commandPaletteOpen).toBe(true);
    act(() => shell().closeCommandPalette());
    expect(shell().commandPaletteOpen).toBe(false);
  });

  it('persists sidebar collapse and drops the legacy key on first toggle', () => {
    localStorage.setItem('research-sidebar-collapsed', '1');
    const shell = mount();
    expect(shell().sidebarCollapsed).toBe(true);
    act(() => shell().toggleSidebar());
    expect(shell().sidebarCollapsed).toBe(false);
    expect(localStorage.getItem('dashboard-sidebar-collapsed')).toBe('0');
    expect(localStorage.getItem('research-sidebar-collapsed')).toBeNull();
  });

  it('applies the collapse default only when no explicit choice is stored', () => {
    localStorage.setItem('dashboard-sidebar-default', 'collapsed');
    expect(mount()().sidebarCollapsed).toBe(true);
  });

  it('persists density, status and group state', () => {
    const shell = mount();
    expect(shell().density).toBe('compact');
    act(() => shell().setDensity('comfortable'));
    act(() => shell().toggleStatus());
    act(() => shell().toggleGroup('portfolio'));
    expect(localStorage.getItem('dashboard-density')).toBe('comfortable');
    expect(localStorage.getItem('dashboard-sidebar-status')).toBe('0');
    expect(JSON.parse(localStorage.getItem('dashboard-sidebar-groups')!)).toEqual(['portfolio']);
  });
});
