"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { attemptLocalBootstrapSignIn } from "@/app/actions/local-bootstrap";

const BOOTSTRAP_STORAGE_KEY = "digichat.localBootstrap.attempted.v1";

/**
 * When DIGICHAT_LOCAL_AUTH_KEY is set (dev only), completes one real Credentials
 * sign-in on the server so the user gets a normal session cookie without /login.
 */
export function LocalBootstrapGate({
  enabled,
  hasServerSession,
}: {
  enabled: boolean;
  hasServerSession: boolean;
}) {
  const router = useRouter();

  useEffect(() => {
    if (!hasServerSession || typeof window === "undefined") return;
    sessionStorage.removeItem(BOOTSTRAP_STORAGE_KEY);
  }, [hasServerSession]);

  useEffect(() => {
    if (!enabled || hasServerSession || typeof window === "undefined") return;
    if (sessionStorage.getItem(BOOTSTRAP_STORAGE_KEY)) return;
    sessionStorage.setItem(BOOTSTRAP_STORAGE_KEY, "1");
    void attemptLocalBootstrapSignIn().then((r) => {
      if (r.ok) {
        router.refresh();
      } else {
        sessionStorage.removeItem(BOOTSTRAP_STORAGE_KEY);
      }
    });
  }, [enabled, hasServerSession, router]);

  return null;
}
