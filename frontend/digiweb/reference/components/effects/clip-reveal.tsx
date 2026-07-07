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

      <div className="clip-band">
        <p className="clip-band-label">incoming band</p>
        <p className="clip-band-copy">
          This surface wipes in via <code>clip-path: inset()</code> on a <code>view()</code>{" "}
          timeline. Scroll it out and back in to replay.
        </p>
      </div>
    </section>
  );
}
