/**
 * SSR smoke for the promoted AuthCard layouts (compact / icons-first / desk).
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AuthCard } from "./AuthCard";

describe("AuthCard", () => {
  it("compact sign-in is logo + fields + icon row + Sign in, no olympus copy", () => {
    const html = renderToStaticMarkup(<AuthCard layout="compact" />);
    expect(html).toContain('data-layout="compact"');
    expect(html).toContain("Sign in");
    expect(html).toContain("Create an account");
    expect(html).toContain('data-testid="login-google"');
    expect(html).toContain('data-testid="login-github"');
    expect(html).toContain('data-testid="login-x"');
    expect(html).toContain("Continue with X");
    expect(html).not.toContain("olympus");
    expect(html).not.toContain("Open the desk");
    expect(html).not.toContain("Continue with Google</button>");
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
    expect(html).not.toContain("olympus");
  });
});
