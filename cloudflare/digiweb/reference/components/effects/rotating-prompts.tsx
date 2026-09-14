/** x.ai's rotating hero teasers + cursor's codebase Q&A, translated: the
 *  prompts are REAL quant questions, and in production each one links into
 *  digichat pre-filled — the teaser is a door, not a poster.
 *  Consumes the shared <RotatingPrompts/> primitive from @digithings/web. */
import { RotatingPrompts as RotatingPromptsLine } from "@digithings/web";

const PROMPTS = [
  "size a kelly-capped BTC position at 2x leverage",
  "explain this drawdown against the regime flags",
  "backtest trend_xsec on ETH, last eight years",
  "which indicators disagree with the entry signal?",
];

export function RotatingPrompts() {
  return (
    <section className="section-block accent-digichat" id="rotating-prompts">
      <p className="kicker">{"// rotating prompts"}</p>
      <h2 className="title">The teaser is a door.</h2>
      <p className="section-copy">
        Rotating hero prompts, but every prompt is a real developer question — never marketing
        copy — and each one opens the live chat pre-filled. Under reduced motion the rotation
        stops on the first prompt.
      </p>

      <RotatingPromptsLine prompts={PROMPTS} className="mt-[1.2rem]" />
    </section>
  );
}
