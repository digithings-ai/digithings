/**
 * @vitest-environment happy-dom
 */
import { createElement, act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const authMock = vi.hoisted(() => ({
  authEnabled: true,
  session: null,
  user: null,
  loading: false,
  signInWithOAuth: vi.fn(async () => {}),
  signInWithPassword: vi.fn(async () => {}),
  signUpWithPassword: vi.fn(async () => {}),
  signOut: vi.fn(async () => {}),
}));

vi.mock('next/link', () => ({
  default: (props: { children?: unknown; href?: string; onClick?: () => void }) =>
    createElement(
      'a',
      { href: props.href, onClick: props.onClick },
      props.children as never,
    ),
}));

vi.mock('@/components/atlas-mark', () => ({ AtlasMark: () => createElement('span', null, 'mark') }));

vi.mock('@/lib/auth-context', () => ({
  useAuth: () => authMock,
}));

import { LoginScreen } from './login-screen';

describe('LoginScreen', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    authMock.authEnabled = true;
    authMock.signInWithOAuth.mockClear();
    authMock.signInWithPassword.mockClear();
    authMock.signUpWithPassword.mockClear();
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

  it('renders oauth-first sign-in grammar', async () => {
    await act(async () => {
      root.render(createElement(LoginScreen));
    });
    expect(container.textContent).toContain('Open the desk.');
    expect(container.textContent).toContain('Continue with Google');
    expect(container.textContent).toContain('Continue with GitHub');
    expect(container.textContent).toContain('Sign in with email');
    expect(container.textContent).toContain('Create an account');
  });

  it('starts Google OAuth from the filled CTA', async () => {
    await act(async () => {
      root.render(createElement(LoginScreen));
    });
    const google = container.querySelector('[data-testid="login-google"]');
    expect(google).not.toBeNull();
    await act(async () => {
      google!.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    expect(authMock.signInWithOAuth).toHaveBeenCalledWith('google');
  });

  it('signup mode shows create-account copy and password strength', async () => {
    await act(async () => {
      root.render(createElement(LoginScreen, { initialMode: 'signup' }));
    });
    expect(container.textContent).toContain('From zero to the desk.');
    expect(container.textContent).toContain('Create account with email');
    expect(container.textContent).toContain('Already on the desk?');
  });

  it('email submit on sign-in calls signInWithPassword', async () => {
    await act(async () => {
      root.render(createElement(LoginScreen));
    });
    const form = container.querySelector('form');
    expect(form).not.toBeNull();
    await act(async () => {
      form!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    });
    expect(authMock.signInWithPassword).toHaveBeenCalled();
  });
});
