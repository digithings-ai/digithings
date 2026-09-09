import { SocialRow } from "@digithings/web";

/**
 * Socials — a quiet utility row of live company profiles. Same borderless
 * glyph buttons as the NavShell GitHub slot, not a marketing share bar and
 * not a fake Connect column. The specimen links the live GitHub, X, and
 * LinkedIn accounts, each opening in a new tab.
 */
export function SocialsReference() {
  return (
    <section className="section-block">
      <p className="kicker">{"// socials"}</p>
      <h2 className="title">Live profiles, quiet buttons.</h2>
      <p className="section-copy">
        Company socials reuse the nav&apos;s borderless icon-button grammar — radius 0, hairline
        rest, phosphor only on focus. The row is a utility, not a share bar: GitHub, X, and
        LinkedIn, each a live profile.
      </p>
      <div className="mt-[1.2rem] inline-flex items-center border border-hair px-[0.7rem] py-[0.35rem]">
        <SocialRow />
      </div>
    </section>
  );
}
