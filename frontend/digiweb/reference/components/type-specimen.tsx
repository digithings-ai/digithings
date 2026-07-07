/**
 * Type specimen — a canonical surface for evaluating the live type suite
 * (switch it in the nav). Shows the three roles at judging scale: the display
 * face big (upright + italic), the body face at reading size, and the mono
 * face with tabular numerals. Everything reads from the --font-* tokens, so the
 * whole specimen re-typesets with the chosen suite — display, body, and mono
 * move together.
 */
export function TypeSpecimen() {
  return (
    <section className="section-block">
      <p className="kicker">{"// type specimen"}</p>
      <h2 className="title">One suite, three voices.</h2>
      <p className="section-copy">
        Swap the type suite in the nav and the whole reference re-typesets — display, body, and
        mono move together as a coordinated set. Judge each here: the display face (claims,
        headlines), the body face (reading), and the mono face (data, labels, numerals).
      </p>

      {/* Token-backed Tailwind utilities via the @theme bridge: font + colour
          utilities (font-display, font-sans, font-mono, text-ink, text-accent)
          emit var(--token), so the specimen re-typesets when the type suite
          switches. spec-row / spec-italic / spec-mono stay as classes — their
          :first-child divider and `em` / `p` child styling live in kept
          combinator rules in the CSS. */}
      <div className="mt-[1.2rem] overflow-hidden rounded-[12px] border border-hair bg-surface/40">
        <div className="spec-row grid grid-cols-[5rem_1fr] gap-[1.2rem] border-t border-hair px-[1.3rem] py-[1.4rem] max-[640px]:grid-cols-1 max-[640px]:gap-[0.6rem]">
          <span className="pt-[0.4rem] font-mono text-[0.58rem] uppercase tracking-[0.12em] text-ink-mute">
            display
          </span>
          <div className="flex flex-wrap items-baseline gap-[1.4rem]">
            <p className="m-0 font-display text-[clamp(3rem,9vw,5.5rem)] font-normal leading-[0.9] text-ink">
              Aa
            </p>
            <div className="min-w-0">
              <p className="m-0 font-display text-[clamp(1.5rem,3.4vw,2.4rem)] font-normal leading-[1.1] tracking-[-0.015em] text-ink">
                Research that ends in an order.
              </p>
              <p className="spec-italic m-0 font-display text-[clamp(1.5rem,3.4vw,2.4rem)] font-normal leading-[1.1] tracking-[-0.015em] text-ink">
                <em>Money-colored, glance-readable.</em>
              </p>
            </div>
          </div>
        </div>

        <div className="spec-row grid grid-cols-[5rem_1fr] gap-[1.2rem] border-t border-hair px-[1.3rem] py-[1.4rem] max-[640px]:grid-cols-1 max-[640px]:gap-[0.6rem]">
          <span className="pt-[0.4rem] font-mono text-[0.58rem] uppercase tracking-[0.12em] text-ink-mute">
            body
          </span>
          <p className="m-0 max-w-[56ch] font-sans text-[1rem] leading-[1.65] text-ink-soft">
            A backtest is a rumor; a tearsheet you can re-run is a receipt. The body voice carries
            the argument between the headlines — long enough to trust, quiet enough to read.
          </p>
        </div>

        <div className="spec-row grid grid-cols-[5rem_1fr] gap-[1.2rem] border-t border-hair px-[1.3rem] py-[1.4rem] max-[640px]:grid-cols-1 max-[640px]:gap-[0.6rem]">
          <span className="pt-[0.4rem] font-mono text-[0.58rem] uppercase tracking-[0.12em] text-ink-mute">
            mono
          </span>
          <div className="spec-mono flex flex-col gap-[0.5rem] font-mono text-[0.95rem] text-ink">
            <p>PF 2.31 · win 64.9% · maxDD −18.4%</p>
            <p className="[font-variant-numeric:tabular-nums] tracking-[0.02em] text-ink-soft">
              0 1 2 3 4 5 6 7 8 9 · $1,284,000 · 63,410.55
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
