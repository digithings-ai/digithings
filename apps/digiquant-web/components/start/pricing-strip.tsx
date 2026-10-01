import { ContactMailto, CtaLink } from "@digithings/ui";
import { Badge } from "@digithings/ui/ui";
import { PRICING_TIERS, type PricingTier } from "../../app/_pricing";

const REPO = "https://github.com/digithings-ai/digithings";
const LOUD = "h-auto w-full px-[1rem] py-[0.7rem] font-mono text-[0.8rem] no-underline";
const GHOST =
  "inline-flex h-auto w-full items-center justify-center border border-hair bg-transparent px-[1rem] py-[0.7rem] text-center font-mono text-[0.8rem] text-ink no-underline hover:bg-surface-2";

function Cta({ tier }: { tier: PricingTier }) {
  if (tier.id === "self") {
    return (
      <CtaLink href={REPO} external variant="default" className={LOUD}>
        Clone the repo
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
    <ul
      aria-label="Pricing tiers"
      className="m-0 grid list-none gap-0 grid-cols-[minmax(0,1fr)] border-x border-t border-hair p-0 min-[860px]:grid-cols-3"
    >
      {PRICING_TIERS.map((tier, i) => (
        <li
          key={tier.id}
          className={`flex flex-col border-b border-hair p-[1.3rem] text-left ${
            i > 0 ? "min-[860px]:border-l" : ""
          } ${tier.featured ? "bg-surface" : ""}`}
        >
          <div className="flex min-h-[1.5rem] items-center justify-between gap-2 font-mono text-[0.68rem] text-ink-mute">
            <span>[ {tier.name.toLowerCase()} ]</span>
            {tier.id === "managed" ? <Badge variant="neutral">in development</Badge> : null}
          </div>
          <p className="m-0 mt-[0.9rem] font-mono text-[1.35rem] leading-none text-ink">
            {tier.price}
            {tier.cadence ? <span className="ml-[0.4rem] text-[0.75rem] text-ink-mute">{tier.cadence}</span> : null}
          </p>
          <p className="m-0 mt-[0.75rem] text-[0.8rem] leading-[1.55] text-ink-soft">{tier.desc}</p>
          <ul className="m-0 mt-[1rem] flex flex-1 list-none flex-col gap-[0.35rem] p-0 font-mono text-[0.72rem] text-ink-soft">
            {tier.features.map((f) => (
              <li key={f} className="flex gap-2">
                <span aria-hidden="true" className="text-ink-mute">
                  +
                </span>
                {f}
              </li>
            ))}
          </ul>
          <div className="mt-[1.3rem]">
            <Cta tier={tier} />
          </div>
        </li>
      ))}
    </ul>
  );
}
