import type { ReactNode } from "react";
import { DeskShell } from "@/components/desk/desk-shell";

/** One shell for every /app page. Client navigation keeps the header and rail. */
export default function DeskLayout({ children }: { children: ReactNode }) {
  return (
    <main id="main" className="h-[100svh]">
      <DeskShell>{children}</DeskShell>
    </main>
  );
}
