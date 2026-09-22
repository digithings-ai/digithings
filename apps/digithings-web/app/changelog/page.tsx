import type { Metadata } from "next";
import { CtaLink, PageHead, RuledList, RuledRow } from "@digithings/ui";
import { DtFooter } from "@/components/DtFooter";
import { DtNav } from "@/components/DtNav";
import releases from "@digithings/design/releases.json";

export const metadata: Metadata = {
  title: "changelog — tagged frontend releases",
  description:
    "Tagged digichat and digiskills releases from the digithings repository. Dates and titles come from the shipped CHANGELOG files, not a marketing rewrite.",
};

type Release = {
  date: string;
  version: string;
  title: string;
  href: string;
  tag: string;
  product: string;
};

const ENTRIES = releases as Release[];

export default function ChangelogPage() {
  return (
    <>
      <DtNav />
      <main id="main" tabIndex={-1}>
        <PageHead kicker="// changelog" title="Tagged releases.">
          Versioned frontend packages only — digichat and digiskills, as published on GitHub.
          The rest of the stack ships on <code className="font-mono text-[0.92em] text-ink">develop</code>
          {" "}without a product tag.
        </PageHead>

        <section className="section pt-0">
          <div className="wrap">
            <RuledList className="mt-[1.2rem]">
              {ENTRIES.map((e) => (
                <RuledRow
                  key={`${e.product}-${e.version}`}
                  term={`[${e.date}] ${e.version}`}
                >
                  <a
                    className="text-ink [text-underline-offset:2px] hover:text-accent"
                    href={e.href}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {e.title}
                  </a>{" "}
                  <span className="font-mono text-[0.78rem] text-ink-mute">[{e.tag}]</span>
                </RuledRow>
              ))}
            </RuledList>
            <div className="mt-[1.6rem]">
              <CtaLink
                href="https://github.com/digithings-ai/digithings/releases"
                external
                variant="ghost"
              >
                All GitHub releases
              </CtaLink>
            </div>
          </div>
        </section>
      </main>
      <DtFooter />
    </>
  );
}
