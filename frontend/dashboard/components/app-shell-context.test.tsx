/**
 * @vitest-environment happy-dom
 */
import { createElement, useEffect } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { act } from 'react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { AppShellProvider, useAppShell } from './app-shell-context';

function Probe({ onReady }: { onReady: (collapsed: boolean, toggle: () => void) => void }) {
  const { sidebarCollapsed, toggleSidebar } = useAppShell();
  useEffect(() => {
    onReady(sidebarCollapsed, toggleSidebar);
  }, [onReady, sidebarCollapsed, toggleSidebar]);
  return null;
}

describe('AppShellProvider sidebar storage', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    localStorage.clear();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    localStorage.clear();
  });

  it('reads the dashboard key and does not write the retired atlas key', () => {
    localStorage.setItem('dashboard-sidebar-collapsed', '1');
    let collapsed = false;
    let toggle = () => {};
    act(() => {
      root.render(
        createElement(
          AppShellProvider,
          null,
          createElement(Probe, {
            onReady: (value, next) => {
              collapsed = value;
              toggle = next;
            },
          }),
        ),
      );
    });
    expect(collapsed).toBe(true);
    act(() => {
      toggle();
    });
    expect(localStorage.getItem('dashboard-sidebar-collapsed')).toBe('0');
    expect(localStorage.getItem('atlas-sidebar-collapsed')).toBeNull();
  });

  it('falls back to the pre-rebrand atlas key, then migrates on toggle', () => {
    localStorage.setItem('atlas-sidebar-collapsed', '1');
    let collapsed = false;
    let toggle = () => {};
    act(() => {
      root.render(
        createElement(
          AppShellProvider,
          null,
          createElement(Probe, {
            onReady: (value, next) => {
              collapsed = value;
              toggle = next;
            },
          }),
        ),
      );
    });
    expect(collapsed).toBe(true);
    act(() => {
      toggle();
    });
    expect(localStorage.getItem('dashboard-sidebar-collapsed')).toBe('0');
    expect(localStorage.getItem('atlas-sidebar-collapsed')).toBeNull();
  });
});
