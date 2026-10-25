import "./home.css";
import Link from "next/link";
import { ContentsOverview } from "@/components/contents-overview";
import { HomeBanner } from "@/components/home-banner";
import { LiverySwitcher } from "@/components/livery-switcher";

/**
 * digiweb — the live design reference.
 *
 * The app was rebuilt on the current generation: shared tokens, the kit, and
 * the brand studio. It replaces the retired 2026-08 blend corpus; every page
 * imports `@digithings/ui` and `@digithings/design` rather than restating them.
 */
export default function ReferencePage() {
  return (
    <main className="reference-page">
      <header className="hero">
        <p className="kicker">{"// digiweb"}</p>
        <h1>
          The design reference, on the <em>current generation</em>.
        </h1>
        <p>
          One live surface for the language every shipped app already speaks: palette roles and
          type from <code>@digithings/design</code>, controls and composites from{" "}
          <code>@digithings/ui</code>, and the brand studio for the mark. Nothing here is a
          screenshot; every page is the code.
        </p>

        <div className="dw-banner" aria-label="digithings wordmark banner">
          <HomeBanner />
        </div>

        <p className="dw-links">
          <Link href="/foundations">Read the foundations →</Link>
          <Link href="/components">Browse the kit →</Link>
          <Link href="/brand/studio">Open the brand studio →</Link>
        </p>
      </header>

      <ContentsOverview />

      <section className="section-block">
        <p className="kicker">{"// what changed"}</p>
        <h2 className="title">Retired corpus, rebuilt surface.</h2>
        <p className="section-copy">
          The old reference app carried fifteen families of specimens from the 2026-08 blend. It
          is gone: this app starts from the current pixel-terminal language and grows by promoting
          a pattern into <code>@digithings/ui</code>, not by parking a copy here. The direction
          proof (<Link href="/rtl">/rtl</Link>) and the brand work survive; the rest is history in
          git.
        </p>
      </section>

      <LiverySwitcher />
    </main>
  );
}
