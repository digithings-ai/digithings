/**
 * @vitest-environment happy-dom
 */
import { createElement, useEffect } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { act } from 'react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

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
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it('owns only the command palette open state (no sidebar/drawer state)', () => {
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
    expect(Object.keys(latest!).sort()).toEqual([
      'closeCommandPalette',
      'commandPaletteOpen',
      'openCommandPalette',
    ]);
    expect(latest!.commandPaletteOpen).toBe(false);
    act(() => latest!.openCommandPalette());
    expect(latest!.commandPaletteOpen).toBe(true);
    act(() => latest!.closeCommandPalette());
    expect(latest!.commandPaletteOpen).toBe(false);
  });
});
