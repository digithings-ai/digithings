/**
 * SSR smoke for the promoted AuthCard layouts (compact / icons-first / desk).
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AuthCard } from "./AuthCard";

describe("AuthCard", () => {
  it("compact sign-in is mark + digiquant wordmark + fields + icon row + Sign in", () => {
    const html = renderToStaticMarkup(<AuthCard layout="compact" />);
    expect(html).toContain('data-layout="compact"');
    expect(html).toContain("acct-auth-wordmark");
    expect(html).toContain("digiquant");
    expect(html).toContain("Sign in");
    expect(html).toContain("Create an account");
    expect(html).toContain('data-testid="login-google"');
    expect(html).toContain('data-testid="login-github"');
    expect(html).toContain('data-testid="login-x"');
    expect(html).toContain('data-testid="login-email-submit"');
    expect(html).toContain('aria-label="X"');
    expect(html).not.toContain("dashboard");
    expect(html).not.toContain("DigiQuant");
    expect(html).not.toContain("Twitter");
    expect(html).not.toContain("Open the desk");
    expect(html).not.toContain("Continue with Google</button>");
    expect(html).not.toContain("Continue with Google");
    expect(html).not.toContain("acct-auth-strength");
  });

  it("compact sign-up still has no strength meter", () => {
    const html = renderToStaticMarkup(
      <AuthCard layout="compact" mode="signup" productName="digiquant" password="Aa1xxxxx" />,
    );
    expect(html).toContain("Sign up");
    expect(html).not.toContain("acct-auth-strength");
  });

  it("icons-first puts oauth above email", () => {
    const html = renderToStaticMarkup(<AuthCard layout="icons-first" />);
    const oauth = html.indexOf("acct-auth-oauth-row");
    const email = html.indexOf('type="email"');
    expect(oauth).toBeGreaterThan(0);
    expect(email).toBeGreaterThan(oauth);
    expect(html).toContain("or email");
  });

  it("desk sign-up adds product kicker and strength meter", () => {
    const html = renderToStaticMarkup(
      <AuthCard layout="desk" mode="signup" productName="digiquant" password="Aa1xxxxx" />,
    );
    expect(html).toContain("digiquant");
    expect(html).toContain("create account");
    expect(html).toContain("Sign up");
    expect(html).toContain("acct-auth-strength");
    expect(html).toContain("strong");
    expect(html).not.toContain("dashboard");
  });
});
