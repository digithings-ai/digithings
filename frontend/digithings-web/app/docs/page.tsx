import type { Metadata } from "next";
import { Footer } from "@digithings/web";
import { DT_FOOTER, DT_FOOTER_META } from "../_nav";
import { DtNav } from "@/components/DtNav";
import { DocsLayout } from "@/components/docs/DocsLayout";

export const metadata: Metadata = {
  title: "docs — the digithings API reference",
  description:
    "API reference for the digithings stack: per-module usage, local deploy, and endpoints. " +
    "Copy any page as Markdown for AI agents. Self-hosted, open core.",
};

// /docs — full API reference with a tier-grouped sidebar, a doc page per module,
// and copy-as-Markdown. Generated from the shared module data so it never drifts.
// Server component; statically exported like the rest of the site.
export default function DocsPage() {
  return (
    <>
      <DtNav />
      <main className="pt-[var(--dq-nav-h)] pb-[clamp(2rem,5vw,4rem)]">
        <DocsLayout />
      </main>
      <Footer links={DT_FOOTER} meta={DT_FOOTER_META} />
    </>
  );
}
