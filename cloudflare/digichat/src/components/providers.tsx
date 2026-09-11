"use client";

import { useEffect } from "react";
import { SessionProvider } from "next-auth/react";
import type { Session } from "next-auth";
import { ThemeProvider } from "@digithings/web";
import { LocalBootstrapGate } from "@/components/local-bootstrap-gate";
import { TooltipProvider } from "@/components/ui/tooltip";
import { BASE_PATH } from "@/lib/base-path";

/**
 * Mirrors every runtime [data-theme] flip on <html> onto the .dark/.light
 * classes — the Tailwind `dark:` variant (globals.css @custom-variant) and the
 * /embed wrapper key off classes. Watching the attribute (rather than wrapping
 * useTheme) covers all writers with one rule: the shared ThemeProvider's
 * toggle/OS-sync AND the /embed tenant-theme override, without forking
 * @digithings/web. The pre-paint twin lives in layout.tsx
 * (themeClassSyncScript) — keep the two in lockstep.
 */
function ThemeClassSync() {
  useEffect(() => {
    const el = document.documentElement;
    const sync = () => {
      const light = el.getAttribute("data-theme") === "light";
      el.classList.toggle("light", light);
      el.classList.toggle("dark", !light);
    };
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(el, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);
  return null;
}

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
      <ThemeProvider>
        <ThemeClassSync />
        <LocalBootstrapGate
          enabled={localBootstrapEnabled}
          hasServerSession={!!session?.user}
        />
        <TooltipProvider delay={200}>{children}</TooltipProvider>
      </ThemeProvider>
    </SessionProvider>
  );
}
