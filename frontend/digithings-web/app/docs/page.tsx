import type { Metadata } from "next";
import { DtFooter } from "@/components/DtFooter";
import { DtNav } from "@/components/DtNav";
import { DocsLayout } from "@/components/docs/DocsLayout";

export const metadata: Metadata = {
  title: "docs — digithings product guides & API reference",
  description:
    "Self-host, digichat install, architecture overview, and per-module API reference for the " +
    "digithings stack. Copy any page as Markdown for AI agents. OpenAPI explorer at /docs/api.",
};

// /docs — product guides + API reference with a tier-grouped sidebar, a doc page
// per module, and copy-as-Markdown. Generated from sharedDocs + module data.
// Server component; statically exported like the rest of the site.
export default function DocsPage() {
  return (
    <>
      <DtNav />
      <main id="main" tabIndex={-1} className="pt-[var(--dq-nav-h)] pb-[clamp(2rem,5vw,4rem)]">
        <DocsLayout />
      </main>
      <DtFooter />
    </>
  );
}
