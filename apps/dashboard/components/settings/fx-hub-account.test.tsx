// @vitest-environment happy-dom
import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const authMock = vi.hoisted(() => ({
  state: {
    user: { email: 'trader@12x.example' } as { email?: string } | null,
    signOut: vi.fn(),
  },
}));

vi.mock('@/lib/auth-context', () => ({
  useAuth: () => authMock.state,
}));

import { FxHubAccount } from './fx-hub-account';

let container: HTMLDivElement | null = null;
let root: Root | null = null;

beforeEach(() => {
  (
    globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
  authMock.state.user = { email: 'trader@12x.example' };
  authMock.state.signOut.mockClear();
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

function render(fxHubGranted: boolean) {
  act(() =>
    root!.render(createElement(FxHubAccount, { fxHubGranted })),
  );
}

describe('FxHubAccount (12x FX Hub-only profile)', () => {
  it('shows the email and the invite-redeemed fact when granted', () => {
    render(true);
    expect(container!.textContent).toContain('trader@12x.example');
    expect(container!.textContent).toContain('Invite redeemed — active');
  });

  it('falls back to signed-out copy and the no-grant line', () => {
    authMock.state.user = null;
    render(false);
    expect(container!.textContent).toContain('not signed in');
    expect(container!.textContent).toContain('No FX Hub grant on this account');
  });

  it('signs out from the account surface', () => {
    render(true);
    const button = container!.querySelector('[data-testid="fx-hub-sign-out"]');
    expect(button).not.toBeNull();
    act(() => {
      (button as HTMLButtonElement).click();
    });
    expect(authMock.state.signOut).toHaveBeenCalledTimes(1);
  });
});
