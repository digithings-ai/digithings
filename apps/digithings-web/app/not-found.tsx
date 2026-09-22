import type { Metadata } from "next";
import { CtaLink, PageHead } from "@digithings/ui";
import { DtNav } from "@/components/DtNav";
import { DtFooter } from "@/components/DtFooter";

export const metadata: Metadata = {
  title: "No such page — digithings",
  description: "The address does not match anything on digithings.ai.",
};

export default function NotFound() {
  return (
    <>
      <DtNav />
      <main id="main" tabIndex={-1} className="pt-[var(--dq-nav-h)]">
        <PageHead kicker="// 404" title="No such page.">
          The address does not match anything on this site. The docs index is the
          fastest way back.
        </PageHead>
        <section className="section">
          <div className="wrap">
            <div className="flex flex-wrap items-center gap-[0.8rem]">
              <CtaLink href="/">Back to top</CtaLink>
              <CtaLink href="/docs" variant="ghost">
                Browse the docs
              </CtaLink>
            </div>
          </div>
        </section>
      </main>
      <DtFooter />
    </>
  );
}
