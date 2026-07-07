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

      <div className="spec">
        <div className="spec-row">
          <span className="spec-role">display</span>
          <div className="spec-display">
            <p className="spec-aa">Aa</p>
            <div className="spec-lines">
              <p className="spec-headline">Research that ends in an order.</p>
              <p className="spec-headline spec-italic">
                <em>Money-colored, glance-readable.</em>
              </p>
            </div>
          </div>
        </div>

        <div className="spec-row">
          <span className="spec-role">body</span>
          <p className="spec-body">
            A backtest is a rumor; a tearsheet you can re-run is a receipt. The body voice carries
            the argument between the headlines — long enough to trust, quiet enough to read.
          </p>
        </div>

        <div className="spec-row">
          <span className="spec-role">mono</span>
          <div className="spec-mono">
            <p>PF 2.31 · win 64.9% · maxDD −18.4%</p>
            <p className="spec-nums">0 1 2 3 4 5 6 7 8 9 · $1,284,000 · 63,410.55</p>
          </div>
        </div>
      </div>
    </section>
  );
}
