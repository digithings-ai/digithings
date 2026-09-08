import type { Metadata } from "next";
import { Footer, Reveal } from "@digithings/web";
import { DQ_FOOTER, DQ_FOOTER_META } from "../_nav";
import { SiteNav } from "@/components/landing/SiteNav";
import { AmbientMesh } from "@/components/landing/AmbientMesh";
import releases from "@digithings/design/releases.json";

export const metadata: Metadata = {
  title: "changelog — tagged stack releases",
  description:
    "Tagged digichat and digiskills releases from the repository this desk is built on. The quant engine ships on develop without a product tag.",
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
      <SiteNav />
      <main className="dq-subpage" id="main" tabIndex={-1}>
        <AmbientMesh />
        <section className="section">
          <div className="wrap">
            <Reveal>
              <div>
                <span className="kicker">{"// changelog"}</span>
                <h1 className="dq-title">Tagged releases.</h1>
                <p className="dq-sub">
                  Versioned packages from the digithings stack this desk is built on. The quant
                  engine and dashboard ship on{" "}
                  <code className="font-mono text-[0.92em] text-ink">develop</code> without a
                  product tag.
                </p>
              </div>
            </Reveal>
            <Reveal>
              <div className="changelog-band mt-[2.2rem]">
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
      <Footer links={DQ_FOOTER} meta={DQ_FOOTER_META} />
    </>
  );
}
