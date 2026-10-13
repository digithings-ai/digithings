import { ContactMailto, CtaLink } from "@digithings/ui";
import { Badge } from "@digithings/ui/ui";
import { PRICING_FAQ, PRICING_TIERS, type PricingTier } from "../../app/_pricing";

const REPO = "https://github.com/digithings-ai/digithings";
const LOUD = "h-7 w-full px-2.5 font-mono text-[0.72rem] no-underline";
const GHOST =
  "inline-flex h-7 w-full items-center justify-center border border-hair bg-transparent px-2.5 text-center font-mono text-[0.72rem] text-ink no-underline hover:bg-surface-2";

function Cta({ tier }: { tier: PricingTier }) {
  if (tier.id === "self") {
    return (
      <CtaLink href={REPO} external variant="default" className={LOUD}>
        View on GitHub
      </CtaLink>
    );
  }
  if (!tier.cta) return null;
  return (
    <ContactMailto email={tier.cta.email} subject={tier.cta.subject} className={GHOST}>
      {tier.cta.label}
    </ContactMailto>
  );
}

/** Three hairline cells straight from PRICING_TIERS. Nothing is added to the
 *  approved copy; the self-hosted cell carries the one loud action. */
export function PricingStrip() {
  return (
    <>
      <ul
        aria-label="Pricing tiers"
        className="m-0 grid list-none grid-cols-1 gap-0 border-x border-t border-hair p-0 min-[860px]:grid-cols-3 min-[860px]:grid-rows-[auto_auto_auto_minmax(0,1fr)_auto]"
      >
        {PRICING_TIERS.map((tier, i) => (
          <li
            key={tier.id}
            className={`flex flex-col gap-2 border-b border-hair px-3 py-2.5 text-left min-[860px]:grid min-[860px]:grid-rows-subgrid min-[860px]:row-span-5 min-[860px]:gap-y-2 ${
              i > 0 ? "min-[860px]:border-s" : ""
            }`}
          >
            <div className="flex items-center justify-between gap-2 font-mono text-[0.64rem] leading-none text-ink-mute">
              <span>[ {tier.name.toLowerCase()} ]</span>
              {tier.id === "managed" ? <Badge variant="neutral">Coming soon</Badge> : null}
            </div>
            <p className="m-0 font-mono text-[1.05rem] leading-none tracking-[-0.02em] text-ink">
              {tier.price}
              {tier.cadence ? (
                <span className="ms-1.5 text-[0.68rem] font-normal text-ink-mute">{tier.cadence}</span>
              ) : null}
            </p>
            <p className="m-0 text-[0.75rem] leading-[1.5] text-ink-soft">{tier.desc}</p>
            <ul className="m-0 flex list-none flex-col gap-1 p-0 font-mono text-[0.66rem] leading-[1.4] text-ink-soft">
              {tier.features.map((f) => (
                <li key={f} className="flex gap-1.5">
                  <span aria-hidden="true" className="text-ink-mute">
                    +
                  </span>
                  {f}
                </li>
              ))}
            </ul>
            <div>
              <Cta tier={tier} />
            </div>
          </li>
        ))}
      </ul>
      <dl className="m-0 border-x border-b border-hair">
        {PRICING_FAQ.map((row, i) => (
          <div
            key={row.q}
            className={`grid gap-1 px-3 py-2 md:grid-cols-[minmax(0,16.5rem)_minmax(0,1fr)] md:items-baseline md:gap-x-4 ${
              i > 0 ? "border-t border-hair" : ""
            }`}
          >
            <dt className="font-mono text-[0.68rem] leading-[1.4] text-ink">{row.q}</dt>
            <dd className="m-0 text-[0.75rem] leading-[1.45] text-ink-soft">{row.a}</dd>
          </div>
        ))}
      </dl>
    </>
  );
}
