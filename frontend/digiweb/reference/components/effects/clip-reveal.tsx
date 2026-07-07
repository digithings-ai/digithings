/** Graphite's band transition: the incoming section wipes in via a clip-path
 *  inset riding the same glide curve as everything else (~0.6s feel). Zero
 *  JS — CSS scroll-driven animation behind @supports, so no support and
 *  reduced motion both get the band simply standing there. */
export function ClipReveal() {
  return (
    <section className="section-block" id="clip-reveal">
      <p className="kicker">{"// clip-path section reveal"}</p>
      <h2 className="title">Bands wipe in, riding the glide.</h2>
      <p className="section-copy">
        The missing transition primitive between page sections: as the band enters the viewport,
        a clip-path inset opens from the bottom edge — scroll-scrubbed, no JS. Use it between
        major bands, never inside them; one wipe per boundary.
      </p>

      {/* The clip-band class stays — the @supports scroll-driven clip-wipe
          animation in effects.css keys off it. Its static box (spacing, border,
          surface, padding) plus the label/copy/code type migrate to token-backed
          Tailwind utilities via the @theme bridge. */}
      <div className="clip-band mt-[1.2rem] rounded-[12px] border border-hair bg-surface px-[1.4rem] py-[2.2rem]">
        <p className="font-mono text-[0.62rem] uppercase tracking-[0.1em] text-accent">incoming band</p>
        <p className="mt-[0.5rem] max-w-[56ch] text-ink-soft">
          This surface wipes in via <code className="font-mono text-[0.82em] text-ink">clip-path: inset()</code> on a{" "}
          <code className="font-mono text-[0.82em] text-ink">view()</code> timeline. Scroll it out and back in to
          replay.
        </p>
      </div>
    </section>
  );
}
