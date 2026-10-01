import type { Metadata } from "next";
import { CtaLink, DocumentFrame, PageTitle } from "@digithings/ui";
import { DtFooter } from "@/components/DtFooter";
import { DtNav } from "@/components/DtNav";

export const metadata: Metadata = {
  title: "No such page — digithings",
  description: "The address does not match anything on digithings.ai.",
};

// The 404, rebuilt on the document grammar (D1, #4429): the same framed column
// and heading scale as every other page, one sentence, and the two ways back —
// the landing page and the docs index. No illustration, no decorative art.

export default function NotFound() {
  return (
    <>
      <DtNav />

      <main id="main" tabIndex={-1} className="pt-[var(--dq-nav-h)]">
        <DocumentFrame>
          <div className="px-[var(--page-pad)] py-[var(--page-step)]">
            <PageTitle path="404" title="No such page.">
              That address does not match anything on this site. Head back to the home page, or
              start from the docs index.
            </PageTitle>
            <div className="mt-[1.4rem] flex flex-wrap items-center gap-[0.8rem]">
              <CtaLink href="/">Home page</CtaLink>
              <CtaLink href="/docs" variant="ghost">
                Browse the docs
              </CtaLink>
            </div>
          </div>
        </DocumentFrame>
      </main>

      <DtFooter />
    </>
  );
}
