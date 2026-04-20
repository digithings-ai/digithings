"use server";

import { signIn } from "@/auth";

/**
 * Performs real Auth.js sign-in via the `local-bootstrap` credentials provider.
 * The key never leaves the server — it is read from DIGICHAT_LOCAL_AUTH_KEY.
 */
export async function attemptLocalBootstrapSignIn(): Promise<{
  ok: boolean;
  error?: string;
}> {
  if (process.env.NODE_ENV === "production") {
    return { ok: false, error: "disabled_in_production" };
  }
  const secret = process.env.DIGICHAT_LOCAL_AUTH_KEY?.trim();
  if (!secret) {
    return { ok: false, error: "not_configured" };
  }
  try {
    await signIn("local-bootstrap", { key: secret, redirect: false });
    return { ok: true };
  } catch (e) {
    const message = e instanceof Error ? e.message : "signin_failed";
    return { ok: false, error: message };
  }
}
