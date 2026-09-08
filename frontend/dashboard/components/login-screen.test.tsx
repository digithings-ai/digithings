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
  signUpWithPassword: vi.fn(async () => ({ session: null })),
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

const replace = vi.hoisted(() => vi.fn());
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace }),
}));

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
    replace.mockClear();
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

  it('renders compact mark + digiquant wordmark + icon oauth + Sign in', async () => {
    await act(async () => {
      root.render(createElement(LoginScreen));
    });
    expect(container.textContent).toContain('digiquant');
    expect(container.textContent).not.toContain('dashboard');
    expect(container.textContent).not.toContain('DigiQuant');
    expect(container.textContent).not.toContain('Open the desk.');
    expect(container.textContent).not.toContain('Continue with Google');
    expect(container.querySelector('[data-testid="login-google"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="login-github"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="login-x"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="login-email-submit"]')?.textContent).toBe(
      'Sign in',
    );
    expect(container.querySelector('[data-testid="login-x"]')?.getAttribute('aria-label')).toBe(
      'X',
    );
    expect(container.textContent).toContain('Create an account');
  });

  it('does not show an invite code field on the OAuth / email card', async () => {
    await act(async () => {
      root.render(createElement(LoginScreen));
    });
    expect(container.querySelector('[data-testid="client-product-invite-input"]')).toBeNull();
    expect(container.querySelector('input[name="invite"]')).toBeNull();
    expect(container.textContent).not.toMatch(/invite code/i);
  });

  it('starts Google OAuth from the Google icon', async () => {
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

  it('starts X OAuth with provider id x', async () => {
    await act(async () => {
      root.render(createElement(LoginScreen));
    });
    const x = container.querySelector('[data-testid="login-x"]');
    expect(x).not.toBeNull();
    await act(async () => {
      x!.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    expect(authMock.signInWithOAuth).toHaveBeenCalledWith('x');
  });

  it('signup mode shows Sign up and a Sign in footer', async () => {
    await act(async () => {
      root.render(createElement(LoginScreen, { initialMode: 'signup' }));
    });
    expect(container.querySelector('[data-testid="login-email-submit"]')?.textContent).toBe(
      'Sign up',
    );
    expect(container.textContent).toContain('Sign in');
    expect(container.textContent).not.toContain('From zero to the desk.');
    expect(container.textContent).not.toContain('Already on the desk?');
  });

  it('empty email submit is refused without calling supabase', async () => {
    await act(async () => {
      root.render(createElement(LoginScreen));
    });
    const form = container.querySelector('form');
    expect(form?.hasAttribute('novalidate')).toBe(true);
    await act(async () => {
      form!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    });
    expect(authMock.signInWithPassword).not.toHaveBeenCalled();
    expect(container.textContent).toContain('8+ character password are required');
    expect(replace).not.toHaveBeenCalled();
  });

  it('valid email submit signs in and replaces home', async () => {
    await act(async () => {
      root.render(createElement(LoginScreen));
    });
    const email = container.querySelector('#acct-email') as HTMLInputElement;
    const password = container.querySelector('#acct-password') as HTMLInputElement;
    await act(async () => {
      const proto = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
      proto?.call(email, 'you@desk.tld');
      email.dispatchEvent(new Event('input', { bubbles: true }));
      proto?.call(password, 'secret12');
      password.dispatchEvent(new Event('input', { bubbles: true }));
    });
    const form = container.querySelector('form');
    await act(async () => {
      form!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    });
    expect(authMock.signInWithPassword).toHaveBeenCalledWith('you@desk.tld', 'secret12');
    expect(replace).toHaveBeenCalledWith('/');
  });

  it('signup with a session replaces home and does not claim email arrived', async () => {
    authMock.signUpWithPassword.mockResolvedValueOnce({ session: { access_token: 'tok' } });
    await act(async () => {
      root.render(createElement(LoginScreen, { initialMode: 'signup' }));
    });
    const email = container.querySelector('#acct-email') as HTMLInputElement;
    const password = container.querySelector('#acct-password') as HTMLInputElement;
    await act(async () => {
      const proto = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
      proto?.call(email, 'you@desk.tld');
      email.dispatchEvent(new Event('input', { bubbles: true }));
      proto?.call(password, 'secret12');
      password.dispatchEvent(new Event('input', { bubbles: true }));
    });
    const form = container.querySelector('form');
    await act(async () => {
      form!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    });
    expect(authMock.signUpWithPassword).toHaveBeenCalledWith('you@desk.tld', 'secret12');
    expect(replace).toHaveBeenCalledWith('/');
    expect(container.textContent).not.toContain('Check your email');
  });

  it('signup without a session tells the truth about Auth SMTP', async () => {
    authMock.signUpWithPassword.mockResolvedValueOnce({ session: null });
    await act(async () => {
      root.render(createElement(LoginScreen, { initialMode: 'signup' }));
    });
    const email = container.querySelector('#acct-email') as HTMLInputElement;
    const password = container.querySelector('#acct-password') as HTMLInputElement;
    await act(async () => {
      const proto = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
      proto?.call(email, 'you@desk.tld');
      email.dispatchEvent(new Event('input', { bubbles: true }));
      proto?.call(password, 'secret12');
      password.dispatchEvent(new Event('input', { bubbles: true }));
    });
    const form = container.querySelector('form');
    await act(async () => {
      form!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    });
    expect(replace).not.toHaveBeenCalled();
    expect(container.textContent).toMatch(/Auth SMTP is not delivering/i);
    expect(container.textContent).not.toContain('Check your email to confirm');
  });
});
