import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { DocsCodeBlock, Reveal, SocialRow } from "@digithings/web";
import { DtFooter } from "@/components/DtFooter";
import { Mono, PageHead, RuledList, RuledRow } from "../_company/prose";
import { ContactMailto } from "@/components/ContactMailto";
import { DtNav } from "@/components/DtNav";
import {
  AVATARS,
  BRAND_DOMAIN,
  BRAND_TAGLINE,
  BRAND_WORD,
  EMAIL_FILES,
  HEADERS,
  OG_CARDS,
  SIGNOFF_TEXT,
} from "@/lib/brandKit";

export const metadata: Metadata = {
  title: "brand — marks, headers, and mail sign-off",
  description:
    "digithings logos, social headers, Open Graph cards, and the company email sign-off. " +
    "Download the files; do not redraw them.",
};

// /brand — the public marketing kit. Artwork is DERIVED (build-avatar.py,
// build-og.py, build-header.py) from the compact terminal mark and the OG
// HEADLINES. This page documents and serves those files; it does not invent a
// tagline, a colour, or a second logo.

function DownloadList({ files }: { files: typeof AVATARS }) {
  return (
    <ul className="m-0 grid list-none gap-0 p-0">
      {files.map((f) => (
        <li
          key={f.href}
          className="flex flex-wrap items-baseline justify-between gap-x-[1rem] gap-y-[0.35rem] border-t border-hair py-[0.85rem] last:border-b"
        >
          <span className="font-mono text-[0.92rem] text-ink">{f.label}</span>
          <span className="text-[0.88rem] text-ink-mute">{f.size}</span>
          <span className="basis-full text-[0.88rem] text-ink-soft sm:basis-auto sm:max-w-[36ch]">
            {f.note}
          </span>
          <a className="font-mono text-[0.8rem] text-accent hover:text-ink" href={f.href} download>
            download
          </a>
        </li>
      ))}
    </ul>
  );
}

export default function BrandPage() {
  return (
    <>
      <DtNav />

      <main id="main" tabIndex={-1} className="pt-[var(--dq-nav-h)]">
        <PageHead kicker={"// brand"} title={<>Marks you can upload.</>}>
          Logos, social headers, the Open Graph card, and the company mail sign-off. Same
          identity as the sites: lowercase {BRAND_WORD}, the block cursor, and the line
          &ldquo;{BRAND_TAGLINE}&rdquo; The files are generated; if one looks wrong, regenerate
          them rather than drawing a new one.
        </PageHead>

        <section className="section">
          <div className="wrap">
            <Reveal className="section-head">
              <span className="kicker">{"// avatars"}</span>
              <h2>Compact d + cursor.</h2>
              <p>
                The reduction of the terminal lockup, derived from{" "}
                <Mono>favicon-dg.svg</Mono> — never hand-drawn. Dark for GitHub, X, and LinkedIn;
                light when the surface is ivory.
              </p>
            </Reveal>
            <div className="mb-[1.6rem] grid max-w-[22rem] grid-cols-2 gap-[1.1rem]">
              <figure className="m-0 border border-hair">
                <Image
                  src="/brand/avatar/digithings-avatar-dark.png"
                  alt="digithings avatar, dark"
                  width={1024}
                  height={1024}
                  className="block h-auto w-full"
                />
                <figcaption className="border-t border-hair px-[0.7rem] py-[0.45rem] font-mono text-[0.72rem] text-ink-mute">
                  dark
                </figcaption>
              </figure>
              <figure className="m-0 border border-hair">
                <Image
                  src="/brand/avatar/digithings-avatar-light.png"
                  alt="digithings avatar, light"
                  width={1024}
                  height={1024}
                  className="block h-auto w-full"
                />
                <figcaption className="border-t border-hair px-[0.7rem] py-[0.45rem] font-mono text-[0.72rem] text-ink-mute">
                  light
                </figcaption>
              </figure>
            </div>
            <DownloadList files={AVATARS} />
          </div>
        </section>

        <section className="section section-alt">
          <div className="wrap">
            <Reveal className="section-head">
              <span className="kicker">{"// social headers"}</span>
              <h2>The OG lockup, shorter.</h2>
              <p>
                Same copy as the Open Graph card, composed for the platform crop — not a 1200×630
                card scaled down. Wordmark, tagline, and {BRAND_DOMAIN} stay inside the visible
                area, including X&apos;s avatar overlap and LinkedIn&apos;s side crop.
              </p>
            </Reveal>
            <div className="mb-[1.6rem] grid gap-[1.1rem]">
              <figure className="m-0 border border-hair">
                <Image
                  src="/brand/headers/digithings-x-1500x500.png"
                  alt="digithings X header, 1500 by 500"
                  width={1500}
                  height={500}
                  className="block h-auto w-full"
                />
                <figcaption className="border-t border-hair px-[0.7rem] py-[0.45rem] font-mono text-[0.72rem] text-ink-mute">
                  X · 1500×500
                </figcaption>
              </figure>
              <figure className="m-0 border border-hair">
                <Image
                  src="/brand/headers/digithings-linkedin-personal-1584x396.png"
                  alt="digithings LinkedIn personal cover, 1584 by 396"
                  width={1584}
                  height={396}
                  className="block h-auto w-full"
                />
                <figcaption className="border-t border-hair px-[0.7rem] py-[0.45rem] font-mono text-[0.72rem] text-ink-mute">
                  LinkedIn personal · 1584×396
                </figcaption>
              </figure>
              <figure className="m-0 border border-hair">
                <Image
                  src="/brand/headers/digithings-linkedin-company-1128x191.png"
                  alt="digithings LinkedIn company cover, 1128 by 191"
                  width={1128}
                  height={191}
                  className="block h-auto w-full"
                />
                <figcaption className="border-t border-hair px-[0.7rem] py-[0.45rem] font-mono text-[0.72rem] text-ink-mute">
                  LinkedIn company · 1128×191
                </figcaption>
              </figure>
            </div>
            <DownloadList files={HEADERS} />
          </div>
        </section>

        <section className="section">
          <div className="wrap">
            <Reveal className="section-head">
              <span className="kicker">{"// open graph"}</span>
              <h2>The card unfurlers already use.</h2>
              <p>
                1200×630, wired through <Mono>openGraph.images</Mono>. Taller than a social header
                — do not crop it to make a banner.
              </p>
            </Reveal>
            <figure className="m-0 mb-[1.6rem] max-w-[40rem] border border-hair">
              <Image
                src="/og.png"
                alt="digithings Open Graph card"
                width={1200}
                height={630}
                className="block h-auto w-full"
              />
              <figcaption className="border-t border-hair px-[0.7rem] py-[0.45rem] font-mono text-[0.72rem] text-ink-mute">
                og.png · 1200×630
              </figcaption>
            </figure>
            <DownloadList files={OG_CARDS} />
          </div>
        </section>

        <section className="section section-alt">
          <div className="wrap">
            <Reveal className="section-head">
              <span className="kicker">{"// email"}</span>
              <h2>Company sign-off.</h2>
              <p>
                Lowercase {BRAND_WORD}, the same tagline as the card, {BRAND_DOMAIN}. No client
                names. HTML uses inline ink because mail clients do not read design tokens.
              </p>
            </Reveal>
            <DocsCodeBlock code={SIGNOFF_TEXT} copyLabel="Copy plaintext sign-off" />
            <div className="mt-[1.2rem]">
              <DownloadList files={EMAIL_FILES} />
            </div>
          </div>
        </section>

        <section className="section">
          <div className="wrap">
            <Reveal className="section-head">
              <span className="kicker">{"// usage"}</span>
              <h2>Where each file goes.</h2>
            </Reveal>
            <RuledList>
              <RuledRow term="X avatar">
                Dark 1024 PNG. Header is the 1500×500 file, not a crop of og.png.
              </RuledRow>
              <RuledRow term="LinkedIn (Chris)">
                Dark 1024 PNG for the photo. Cover is the 1584×396 personal file.
              </RuledRow>
              <RuledRow term="LinkedIn (company)">
                Same avatar. Cover is the 1128×191 company file.
              </RuledRow>
              <RuledRow term="GitHub org">
                Dark 1024 PNG. Canonical path{" "}
                <Mono>frontend/digiweb/brand/avatar/</Mono> — this page serves a checked copy.
              </RuledRow>
              <RuledRow term="Polarity">
                Dark canvas and light ink, or the inverse. Values live in{" "}
                <Mono>frontend/digiweb/brand/README.md</Mono>. No other hues.
              </RuledRow>
              <RuledRow term="Regenerate">
                <Mono>python3 frontend/digiweb/brand/build-header.py</Mono> writes headers and
                refreshes the copies this page serves.{" "}
                <Mono>--check</Mono> fails if they drift.
              </RuledRow>
            </RuledList>
            <p className="mt-[1.8rem] max-w-[64ch] text-[0.95rem] leading-[1.7] text-ink-soft">
              Questions about a listing or a slide:{" "}
              <ContactMailto className="text-accent hover:text-ink">email us</ContactMailto>
              . The kit folder in the repository remains the one place to look for off-repo
              uploads. Live profiles:
            </p>
            <div className="mt-[0.9rem]">
              <SocialRow />
            </div>
            <p className="mt-[1rem]">
              <Link className="btn btn-ghost" href="/about">
                About digithings <span aria-hidden="true">→</span>
              </Link>
            </p>
          </div>
        </section>
      </main>

      <DtFooter />
    </>
  );
}
