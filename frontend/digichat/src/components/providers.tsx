"use client";

import { SessionProvider } from "next-auth/react";
import type { Session } from "next-auth";
import { LocalBootstrapGate } from "@/components/local-bootstrap-gate";
import { TooltipProvider } from "@/components/ui/tooltip";
import { BASE_PATH } from "@/lib/base-path";

export function Providers({
  children,
  session,
  localBootstrapEnabled,
}: {
  children: React.ReactNode;
  session: Session | null;
  /** True when DIGICHAT_LOCAL_AUTH_KEY is set (non-production); triggers real signIn once. */
  localBootstrapEnabled: boolean;
}) {
  return (
    <SessionProvider session={session} basePath={`${BASE_PATH}/api/auth`}>
      <LocalBootstrapGate
        enabled={localBootstrapEnabled}
        hasServerSession={!!session?.user}
      />
      <TooltipProvider delay={200}>{children}</TooltipProvider>
    </SessionProvider>
  );
}
