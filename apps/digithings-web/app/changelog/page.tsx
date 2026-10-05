import type { Metadata } from "next";
import {
  CtaLink,
  DocumentFrame,
  PageTitle,
  ReleaseRail,
  Section,
  type ReleaseRailItem,
} from "@digithings/ui";
import { DtFooter } from "@/components/DtFooter";
import { DtNav } from "@/components/DtNav";
import releases from "@digithings/design/releases.json";

export const metadata: Metadata = {
  title: "changelog — tagged frontend releases",
  description:
    "Tagged digichat and digiskills releases from the digithings repository. Dates and titles come from the shipped CHANGELOG files, not a marketing rewrite.",
};

// /changelog — the release rows on the document grammar (D1, #4429): one framed
// column, a PageTitle and a single section holding the ReleaseRail. No bands,
// no bracketed ruled list. The rows are the data file verbatim (newest first);
// the only mapping is that `releases.json` stores the published label as
// "digichat v2.3.1" while the rail already prints the product on its own line,
// so the redundant product prefix is stripped and the version stays the link.

type Release = {
  date: string;
  version: string;
  title: string;
  href: string;
  tag?: string;
  product: string;
};

const ENTRIES: ReleaseRailItem[] = (releases as Release[]).map((release) => ({
  product: release.product,
  version: release.version.replace(`${release.product} `, ""),
  date: release.date,
  title: release.title,
  href: release.href,
  tag: release.tag,
}));

export default function ChangelogPage() {
  return (
    <>
      <DtNav />

      <main id="main" tabIndex={-1} className="pt-[var(--dq-nav-h)]">
        <DocumentFrame>
          <div className="px-[var(--page-pad)] py-[var(--page-step)]">
            <PageTitle path="changelog" title="Tagged releases.">
              Release notes for the versioned packages, digichat and digiskills, as published on
              GitHub.
            </PageTitle>
          </div>

          <Section
            id="releases"
            title="Releases"
            lede="Newest first, taken directly from each package's CHANGELOG. The rest of the stack ships continuously without a version tag."
          >
            <ReleaseRail items={ENTRIES} />
            <div className="mt-[1.6rem]">
              <CtaLink
                href="https://github.com/digithings-ai/digithings/releases"
                external
                variant="ghost"
              >
                All GitHub releases
              </CtaLink>
            </div>
          </Section>
        </DocumentFrame>
      </main>

      <DtFooter />
    </>
  );
}
