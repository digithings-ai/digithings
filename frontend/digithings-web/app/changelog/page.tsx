import type { Metadata } from "next";
import { Footer, Reveal } from "@digithings/web";
import { DT_FOOTER, DT_FOOTER_META } from "../_nav";
import { PageHead } from "../_company/prose";
import { DtNav } from "@/components/DtNav";
import releases from "../../../digiweb/design/releases.json";

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
            <Reveal>
              <div className="changelog-band">
                {ENTRIES.map((e) => (
                  <div className="changelog-row" key={`${e.product}-${e.version}`}>
                    <div className="changelog-row__date">
                      {e.date} · {e.version}
                    </div>
                    <div className="changelog-row__title">
                      <a href={e.href} target="_blank" rel="noopener noreferrer">
                        {e.title}
                      </a>
                      <span className="changelog-row__tag">{e.tag}</span>
                    </div>
                  </div>
                ))}
              </div>
              <p className="changelog-band__footer">
                <a
                  href="https://github.com/digithings-ai/digithings/releases"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  All GitHub releases →
                </a>
              </p>
            </Reveal>
          </div>
        </section>
      </main>
      <Footer links={DT_FOOTER} meta={DT_FOOTER_META} />
    </>
  );
}
