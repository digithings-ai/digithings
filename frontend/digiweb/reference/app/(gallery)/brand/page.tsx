import Image from "next/image";
import Link from "next/link";
import { DocsCodeBlock } from "@digithings/web";
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

/**
 * Brand kit — avatars, social headers, OG card, mail sign-off.
 *
 * Local design-reference only (`npm run dev --workspace design-reference`).
 * Not shipped on digithings.ai. Artwork is DERIVED (build-avatar.py,
 * build-og.py, build-header.py); this page documents and serves those files.
 */

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
    <main className="reference-page">
      <header className="hero">
        <p className="kicker">{"// brand"}</p>
        <h1>
          Marks you can <em>upload.</em>
        </h1>
        <p>
          Logos, social headers, the Open Graph card, and the company mail sign-off. Same identity
          as the sites: lowercase {BRAND_WORD}, the block cursor, and the line &ldquo;
          {BRAND_TAGLINE}&rdquo; The files are generated; if one looks wrong, regenerate them rather
          than drawing a new one. This page is the design-reference kit — it is not a public
          marketing URL.
        </p>
      </header>

      <section className="section-block" id="avatars">
        <p className="kicker">{"// avatars"}</p>
        <h2 className="title">Compact d + cursor.</h2>
        <p className="section-copy">
          The reduction of the terminal lockup, derived from <code>favicon-dg.svg</code> — never
          hand-drawn. Dark for GitHub, X, and LinkedIn; light when the surface is ivory.
        </p>
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
      </section>

      <section className="section-block" id="social-headers">
        <p className="kicker">{"// social headers"}</p>
        <h2 className="title">The OG lockup, shorter.</h2>
        <p className="section-copy">
          Same copy as the Open Graph card, composed for the platform crop — not a 1200×630 card
          scaled down. Wordmark, tagline, and {BRAND_DOMAIN} stay inside the visible area, including
          X&apos;s avatar overlap and LinkedIn&apos;s side crop.
        </p>
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
      </section>

      <section className="section-block" id="open-graph">
        <p className="kicker">{"// open graph"}</p>
        <h2 className="title">The card unfurlers already use.</h2>
        <p className="section-copy">
          1200×630, wired through each live site&apos;s <code>openGraph.images</code>. Taller than a
          social header — do not crop it to make a banner.
        </p>
        <figure className="m-0 mb-[1.6rem] max-w-[40rem] border border-hair">
          <Image
            src="/brand/og/digithings-og.png"
            alt="digithings Open Graph card"
            width={1200}
            height={630}
            className="block h-auto w-full"
          />
          <figcaption className="border-t border-hair px-[0.7rem] py-[0.45rem] font-mono text-[0.72rem] text-ink-mute">
            digithings-og.png · 1200×630
          </figcaption>
        </figure>
        <DownloadList files={OG_CARDS} />
      </section>

      <section className="section-block" id="email">
        <p className="kicker">{"// email"}</p>
        <h2 className="title">Company sign-off.</h2>
        <p className="section-copy">
          Lowercase {BRAND_WORD}, the same tagline as the card, {BRAND_DOMAIN}. No client names. HTML
          uses inline ink because mail clients do not read design tokens.
        </p>
        <DocsCodeBlock code={SIGNOFF_TEXT} copyLabel="Copy plaintext sign-off" />
        <div className="mt-[1.2rem]">
          <DownloadList files={EMAIL_FILES} />
        </div>
      </section>

      <section className="section-block" id="usage">
        <p className="kicker">{"// usage"}</p>
        <h2 className="title">Where each file goes.</h2>
        <dl className="m-0 grid gap-0">
          <div className="border-t border-hair py-[0.85rem]">
            <dt className="font-mono text-[0.82rem] text-ink">X avatar</dt>
            <dd className="m-0 mt-[0.25rem] text-[0.92rem] text-ink-soft">
              Dark 1024 PNG. Header is the 1500×500 file, not a crop of og.png.
            </dd>
          </div>
          <div className="border-t border-hair py-[0.85rem]">
            <dt className="font-mono text-[0.82rem] text-ink">LinkedIn (Chris)</dt>
            <dd className="m-0 mt-[0.25rem] text-[0.92rem] text-ink-soft">
              Dark 1024 PNG for the photo. Cover is the 1584×396 personal file.
            </dd>
          </div>
          <div className="border-t border-hair py-[0.85rem]">
            <dt className="font-mono text-[0.82rem] text-ink">LinkedIn (company)</dt>
            <dd className="m-0 mt-[0.25rem] text-[0.92rem] text-ink-soft">
              Same avatar. Cover is the 1128×191 company file.
            </dd>
          </div>
          <div className="border-t border-hair py-[0.85rem]">
            <dt className="font-mono text-[0.82rem] text-ink">GitHub org</dt>
            <dd className="m-0 mt-[0.25rem] text-[0.92rem] text-ink-soft">
              Dark 1024 PNG. Canonical path <code>frontend/digiweb/brand/avatar/</code> — this page
              serves a checked copy.
            </dd>
          </div>
          <div className="border-t border-hair py-[0.85rem]">
            <dt className="font-mono text-[0.82rem] text-ink">Polarity</dt>
            <dd className="m-0 mt-[0.25rem] text-[0.92rem] text-ink-soft">
              Dark canvas and light ink, or the inverse. Values live in{" "}
              <code>frontend/digiweb/brand/README.md</code>. No other hues.
            </dd>
          </div>
          <div className="border-t border-hair py-[0.85rem] last:border-b">
            <dt className="font-mono text-[0.82rem] text-ink">Regenerate</dt>
            <dd className="m-0 mt-[0.25rem] text-[0.92rem] text-ink-soft">
              <code>python3 frontend/digiweb/brand/build-header.py</code> writes headers and
              refreshes the copies this page serves. <code>--check</code> fails if they drift.
            </dd>
          </div>
        </dl>
        <p className="section-copy mt-[1.8rem]">
          The kit folder in the repository remains the one place to look for off-repo uploads. Marks
          in code live on{" "}
          <Link className="text-accent hover:text-ink" href="/symbols">
            /symbols
          </Link>
          .
        </p>
      </section>
    </main>
  );
}
