/**
 * NumberedStages — the sequential-stage grammar promoted from the design
 * reference (layout-patterns/numbered-stages): a numbered spine where each
 * step is one move in the flow — big mono index badge, an optional mono
 * micro-caps tag, a serif title, one sentence of mechanism. A hairline spine
 * (`.ns-stage::before`, styles/stages.css) runs through the badge column and
 * stops at the last stage; each stage may scope its own module livery via
 * `livery` (`accent-<module>` — declared in @digithings/design/tokens.css),
 * which re-tints the badge's two-color color-mix and the tag/index text.
 *
 * Server component — no state, no effects. Wiring (in the consuming app):
 *   globals.css   @import "@digithings/web/styles/stages.css";
 *                 @source "<path-to>/digiweb/web/src/components/stages";
 */
export type NumberedStage = {
  /** Big mono index rendered in the spine badge — "1.0", "01", "a" … */
  num: string;
  /** Serif stage title. */
  title: string;
  /** One sentence of mechanism under the title. */
  mech: string;
  /** Optional mono micro-caps tag above the title (module name, phase …). */
  tag?: string;
  /** Optional module livery scope — suffix of an `accent-<module>` class. */
  livery?: string;
};

export function NumberedStages({
  stages,
  className,
}: {
  stages: NumberedStage[];
  className?: string;
}) {
  return (
    <ol className={`grid list-none gap-0 p-0${className ? ` ${className}` : ""}`}>
      {stages.map((s) => (
        <li
          key={s.num}
          className={`ns-stage relative grid grid-cols-[3.4rem_1fr] gap-[1.1rem] pb-[1.8rem]${
            s.livery ? ` accent-${s.livery}` : ""
          }`}
        >
          <span className="ns-node" aria-hidden="true">
            {s.num}
          </span>
          <div className="pt-[0.1rem]">
            {s.tag ? (
              <p className="font-mono text-[0.6rem] uppercase tracking-[0.12em] text-accent">
                {s.tag}
              </p>
            ) : null}
            <h3 className="mt-[0.2rem] font-display font-normal text-[clamp(1.2rem,2.4vw,1.5rem)] tracking-[-0.013em] text-ink">
              {s.title}
            </h3>
            <p className="mt-[0.35rem] max-w-[52ch] text-[0.9rem] text-ink-soft">{s.mech}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}
