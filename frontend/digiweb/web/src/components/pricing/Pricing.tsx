/**
 * Pricing — the open-core tier-card family. `PricingTierCard` is one hairline
 * card: name, mono price line, soft description, ✓-marked feature list
 * (check-marker grammar in styles/pricing.css), and a CTA slot; `accent`
 * tints the featured tier (two-color mix, also styles/pricing.css). The
 * `variant` picks a density: "compact" is the reference/catalog voice,
 * "hero" the marketing-page voice (digiquant contact tiers). `Pricing` lays
 * cards out on the two-up grid with an optional hairline trust line;
 * `PrecisionTable` is the per-unit price table riding the tearsheet
 * hairline-row, mono-numeral voice. Every name, price, feature and CTA
 * arrives as a prop — nothing product-specific baked in. Static display
 * components; no client state.
 */
import type { ElementType, ReactNode } from "react";

const cx = (...parts: Array<string | false | undefined>) => parts.filter(Boolean).join(" ");

export interface PricingTierCardProps {
  /** Tier name, e.g. "Self-hosted". */
  name: ReactNode;
  /** Element rendered for the name (default "p"; marketing pages want "h3"). */
  nameAs?: ElementType;
  /** Mono sub-line under the name ("$40/mo", "open core · free", "contact us"). */
  priceLine?: ReactNode;
  /** Soft body copy under the name/price line. */
  description?: ReactNode;
  /** ✓-marked feature rows — the check-marker grammar. */
  features?: ReactNode[];
  /** CTA slot — the caller brings its own button/anchor dressing (btn-*). */
  cta?: ReactNode;
  /** Featured tier: accent-tinted border + wash (styles/pricing.css). */
  accent?: boolean;
  /** Density: "compact" (reference/catalog) or "hero" (marketing page). */
  variant?: "compact" | "hero";
  className?: string;
}

/** One pricing tier card. Composable alone (apps own their grid) or via <Pricing/>. */
export function PricingTierCard({
  name,
  nameAs: NameTag = "p",
  priceLine,
  description,
  features,
  cta,
  accent = false,
  variant = "compact",
  className,
}: PricingTierCardProps) {
  const hero = variant === "hero";
  return (
    <div
      className={cx(
        "border",
        hero ? "rounded-[var(--r-md)] px-[1.8rem] py-[2rem]" : "rounded-[12px] p-[1.1rem]",
        accent ? "pricing-tier-accent" : "border-hair bg-surface",
        className,
      )}
    >
      <NameTag className={hero ? "text-[1.4rem] font-semibold tracking-[-0.02em]" : "text-[1rem]"}>
        {name}
      </NameTag>
      {priceLine != null ? (
        <p
          className={cx(
            "mt-[0.4rem] font-mono text-ink-soft",
            hero ? "text-[0.95rem]" : "text-[0.78rem]",
          )}
        >
          {priceLine}
        </p>
      ) : null}
      {description != null ? (
        <p className="mt-[0.4rem] text-[0.85rem] text-ink-soft">{description}</p>
      ) : null}
      {features && features.length > 0 ? (
        <ul
          className={cx(
            "m-0 flex list-none flex-col gap-[0.55rem] p-0 text-[0.9rem] text-ink-soft",
            hero ? "mt-[1.3rem]" : "mt-[0.8rem]",
          )}
        >
          {features.map((feature, i) => (
            <li key={i} className="pricing-feature flex items-start gap-[0.55rem]">
              {feature}
            </li>
          ))}
        </ul>
      ) : null}
      {cta != null ? <div className={hero ? "mt-[1.6rem]" : "mt-[0.9rem]"}>{cta}</div> : null}
    </div>
  );
}

export interface PricingProps {
  /** Tier cards, left to right. */
  tiers: PricingTierCardProps[];
  /** Hairline-ruled trust line under the grid ("Free for 30 days…"). */
  footnote?: ReactNode;
  /** Density forwarded to every tier card (a tier's own `variant` wins). */
  variant?: "compact" | "hero";
  /** Extra classes on the grid (e.g. "mt-[1.2rem]"). */
  className?: string;
}

/** Tier cards on the reference two-up grid, plus the optional trust line. */
export function Pricing({ tiers, footnote, variant = "compact", className }: PricingProps) {
  return (
    <>
      <div className={cx("grid grid-cols-2 gap-[0.9rem]", className)}>
        {tiers.map((tier, i) => (
          <PricingTierCard key={i} variant={variant} {...tier} />
        ))}
      </div>
      {footnote != null ? (
        <p className="mt-[0.9rem] border-t border-hair pt-[0.9rem] text-[0.82rem] text-ink-mute">
          {footnote}
        </p>
      ) : null}
    </>
  );
}

export interface PrecisionTableProps {
  /** Column headers; the last column right-aligns (numerals live there). */
  columns: ReactNode[];
  /** Row cells, one array per row; the first cell carries full ink. */
  rows: ReactNode[][];
  /** Extra classes on the table (e.g. "mt-[1.2rem]"). */
  className?: string;
}

/** Per-unit price table — hairline rows, mono numerals, right-aligned tail column. */
export function PrecisionTable({ columns, rows, className }: PrecisionTableProps) {
  const last = columns.length - 1;
  return (
    <table className={cx("w-full border-collapse font-mono text-[0.76rem]", className)}>
      <thead>
        <tr>
          {columns.map((column, i) => (
            <th
              key={i}
              scope="col"
              className={cx(
                "border-b border-hair pb-[0.5rem] text-[0.6rem] uppercase tracking-[0.08em] text-ink-mute",
                i === last ? "text-right" : "text-left",
              )}
            >
              {column}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, ri) => (
          <tr key={ri}>
            {row.map((cell, ci) => (
              <td
                key={ci}
                className={cx(
                  "border-b border-hair py-[0.55rem]",
                  ci === 0 ? "text-ink" : "text-ink-soft",
                  ci === last && "text-right",
                )}
              >
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
