// @vitest-environment happy-dom
import { act, createElement, type ReactNode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const guardMock = vi.hoisted(() => ({
  state: { canFxHub: true, fxHubOnlyInvitee: true },
}));
const pathMock = vi.hoisted(() => ({ value: '/portfolio' }));
const replaceMock = vi.hoisted(() => vi.fn());

vi.mock('next/navigation', () => ({
  usePathname: () => pathMock.value,
  useRouter: () => ({ replace: replaceMock }),
}));

vi.mock('@/lib/fx-hub-only', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/fx-hub-only')>();
  return { ...actual, useFxHubOnlyInvitee: () => guardMock.state };
});

import FxHubOnlyGuard from './fx-hub-only-guard';

let container: HTMLDivElement | null = null;
let root: Root | null = null;

beforeEach(() => {
  (
    globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
  guardMock.state = { canFxHub: true, fxHubOnlyInvitee: true };
  pathMock.value = '/portfolio';
  replaceMock.mockClear();
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  container = null;
  root = null;
});

function render(ui: ReactNode) {
  act(() => root!.render(createElement(FxHubOnlyGuard, null, ui)));
}

describe('FxHubOnlyGuard', () => {
  it('redirects an fx_hub-only invitee off non-FX-Hub routes', () => {
    render(createElement('span', { 'data-guard-child': '1' }, 'child'));
    expect(container!.querySelector('[data-guard-child]')).toBeNull();
    expect(replaceMock).toHaveBeenCalledWith('/twelve-x');
  });

  it('renders FX Hub and settings routes for the invitee', () => {
    pathMock.value = '/twelve-x';
    render(createElement('span', { 'data-guard-child': '1' }, 'child'));
    expect(container!.querySelector('[data-guard-child]')).not.toBeNull();
    expect(replaceMock).not.toHaveBeenCalled();

    pathMock.value = '/settings/billing';
    render(createElement('span', { 'data-guard-child': '1' }, 'child'));
    expect(container!.querySelector('[data-guard-child]')).not.toBeNull();
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it('leaves non-invitee accounts untouched', () => {
    guardMock.state = { canFxHub: false, fxHubOnlyInvitee: false };
    render(createElement('span', { 'data-guard-child': '1' }, 'child'));
    expect(container!.querySelector('[data-guard-child]')).not.toBeNull();
    expect(replaceMock).not.toHaveBeenCalled();
  });
});
