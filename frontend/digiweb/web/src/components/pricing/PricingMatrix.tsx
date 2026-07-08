"use client";
/**
 * PricingMatrix — the grouped feature-comparison matrix (Graphite grammar):
 * tier column headers with a mono price line + CTA slot, an optional billing
 * toggle, uppercase group rows, plain-word cells ("✓ · Limited · Advanced";
 * a "—" cell reads muted), and one continuous accent-tinted band down the
 * `popular` tier (header + body). Billing-dependent prices arrive precomputed
 * (`priceMonthly` / `priceAnnual`) so server components can pass plain nodes;
 * the toggle only picks between them. Tier names, prices, CTAs, toggle and
 * popular labels are all props — nothing product-specific baked in. Static
 * structure is token-backed utilities; the toggle switch (ancestor `.on`
 * state + two-color mix + knob translate) lives in styles/pricing.css.
 */
import { useId, useState, type ReactNode } from "react";

const cx = (...parts: Array<string | false | undefined>) => parts.filter(Boolean).join(" ");

export interface PricingMatrixTier {
  name: ReactNode;
  /** Billing-independent price line ("Free", "Let's talk"). Wins over the pair. */
  price?: ReactNode;
  /** Price line while the toggle is off (monthly billing). */
  priceMonthly?: ReactNode;
  /** Price line while the toggle is on (annual billing). */
  priceAnnual?: ReactNode;
  /** CTA slot — the caller brings its own button/anchor dressing (btn-*). */
  cta?: ReactNode;
  /** Tinted column band + accent top rule + the `popularLabel` flag. */
  popular?: boolean;
}

export interface PricingMatrixRow {
  label: ReactNode;
  /** One cell per tier, in tier order; a cell that is exactly "—" renders muted. */
  cells: ReactNode[];
}

export interface PricingMatrixGroup {
  label: ReactNode;
  rows: PricingMatrixRow[];
}

export interface PricingMatrixProps {
  tiers: PricingMatrixTier[];
  groups: PricingMatrixGroup[];
  /** Billing-toggle label ("Annual billing (20% off)"); omit to hide the toggle. */
  toggleLabel?: ReactNode;
  /** Initial toggle state. Default true (annual). */
  defaultAnnual?: boolean;
  /** Flag under the popular tier's CTA (e.g. "Most popular"). */
  popularLabel?: ReactNode;
  /** Accessible name for the empty feature-label column header. */
  featureColumnLabel?: string;
  /** Extra classes on the toggle row (e.g. "mt-[1.2rem]"). */
  toggleClassName?: string;
  /** Extra classes on the table's scroll wrapper (e.g. "mt-4"). */
  className?: string;
}

/** Grouped tier-comparison table with an optional annual-billing toggle. */
export function PricingMatrix({
  tiers,
  groups,
  toggleLabel,
  defaultAnnual = true,
  popularLabel,
  featureColumnLabel = "Feature",
  toggleClassName,
  className,
}: PricingMatrixProps) {
  const [annual, setAnnual] = useState(defaultAnnual);
  const toggleLabelId = useId();
  const priceOf = (tier: PricingMatrixTier) =>
    tier.price ?? (annual ? tier.priceAnnual : tier.priceMonthly);

  return (
    <>
      {toggleLabel != null ? (
        <div className={cx("flex items-center gap-[0.6rem]", toggleClassName)}>
          <button
            type="button"
            className={`pm-toggle${annual ? " on" : ""}`}
            role="switch"
            aria-checked={annual}
            aria-labelledby={toggleLabelId}
            onClick={() => setAnnual((v) => !v)}
          >
            <span className="pm-knob" aria-hidden="true" />
          </button>
          <span id={toggleLabelId} className="font-mono text-[0.72rem] text-ink-soft">
            {toggleLabel}
          </span>
        </div>
      ) : null}

      <div className={cx("overflow-x-auto", className)}>
        <table className="w-full min-w-[640px] border-collapse text-[0.82rem]">
          <thead>
            <tr>
              <th
                scope="col"
                aria-label={featureColumnLabel}
                className="border-b border-hair pt-[0.8rem] pr-[0.9rem] pb-[1rem] pl-0 text-left align-top"
              />
              {tiers.map((tier, i) => (
                <th
                  scope="col"
                  key={i}
                  className={cx(
                    "border-b border-hair px-[0.9rem] pt-[0.8rem] pb-[1rem] text-left align-top",
                    tier.popular && "rounded-t-[8px] border-t-2 border-t-accent bg-accent/6",
                  )}
                >
                  <span className="block text-[0.95rem]">{tier.name}</span>
                  <span className="mt-[0.25rem] mb-[0.7rem] block font-mono text-[0.78rem] text-ink-soft">
                    {priceOf(tier)}
                  </span>
                  {tier.cta}
                  {tier.popular && popularLabel != null ? (
                    <span className="mt-[0.5rem] block font-mono text-[0.58rem] uppercase tracking-[0.08em] text-accent">
                      {popularLabel}
                    </span>
                  ) : null}
                </th>
              ))}
            </tr>
          </thead>
          {groups.map((group, gi) => (
            <tbody key={gi}>
              <tr>
                <th
                  scope="rowgroup"
                  colSpan={tiers.length + 1}
                  className="px-0 pt-[1rem] pb-[0.4rem] text-left font-mono text-[0.62rem] font-normal uppercase tracking-[0.1em] text-ink-mute"
                >
                  {group.label}
                </th>
              </tr>
              {group.rows.map((row, ri) => (
                <tr key={ri}>
                  <th
                    scope="row"
                    className="border-b border-hair/60 py-[0.55rem] pr-[0.9rem] pl-0 text-left font-normal text-ink-soft"
                  >
                    {row.label}
                  </th>
                  {row.cells.map((cell, ci) => (
                    <td
                      key={ci}
                      className={cx(
                        "border-b border-hair/60 px-[0.9rem] py-[0.55rem] font-mono text-[0.74rem]",
                        cell === "—" && "text-ink-mute",
                        tiers[ci]?.popular && "bg-accent/6",
                      )}
                    >
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          ))}
        </table>
      </div>
    </>
  );
}
