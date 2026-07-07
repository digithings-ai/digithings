"use client";

import { useState } from "react";

/** Graphite's pricing system: grouped comparison rows, ✓/Limited/Advanced
 *  cells, an annual toggle (20% off), per-tier CTA verbs that escalate with
 *  commitment — and enterprise never shows a price. */
type Tier = {
  name: string;
  monthly: number | null;
  cta: string;
  kind: "quiet" | "primary" | "ghost";
  popular?: boolean;
};

const TIERS: Tier[] = [
  { name: "Hobby", monthly: 0, cta: "Sign up", kind: "quiet" },
  { name: "Team", monthly: 40, cta: "Start free trial", kind: "primary", popular: true },
  { name: "Enterprise", monthly: null, cta: "Request a demo", kind: "ghost" },
];

const GROUPS: { group: string; rows: { label: string; cells: [string, string, string] }[] }[] = [
  {
    group: "Backtesting",
    rows: [
      { label: "Strategies", cells: ["3", "Unlimited", "Unlimited"] },
      { label: "Bar history", cells: ["Limited", "Full", "Full"] },
      { label: "Walk-forward optimize", cells: ["—", "✓", "✓"] },
    ],
  },
  {
    group: "Live",
    rows: [
      { label: "Paper trading", cells: ["✓", "✓", "✓"] },
      { label: "Live adapters", cells: ["—", "Basic", "Advanced"] },
      { label: "Kill-switch SLA", cells: ["—", "—", "✓"] },
    ],
  },
  {
    group: "Support",
    rows: [
      { label: "Audit log", cells: ["—", "✓", "✓"] },
      { label: "SSO", cells: ["—", "—", "✓"] },
    ],
  },
];

export function PricingMatrixReference() {
  const [annual, setAnnual] = useState(true);

  const price = (monthly: number | null) => {
    if (monthly === null) return null;
    if (monthly === 0) return "Free";
    const value = annual ? Math.round(monthly * 0.8) : monthly;
    return `$${value}/mo`;
  };

  return (
    <section className="section-block" id="pricing-matrix">
      <p className="kicker">{"// comparison matrix"}</p>
      <h2 className="title">CTA verbs escalate with commitment.</h2>
      <p className="section-copy">
        Grouped rows, plain-word cells (✓ · Limited · Basic · Advanced), an annual toggle worth
        exactly what it says, and a different verb per tier: sign up, start, request. Enterprise
        never shows a price.
      </p>

      <div className="mt-[1.2rem] flex items-center gap-[0.6rem]">
        <button
          type="button"
          className={`pm-toggle${annual ? " on" : ""}`}
          role="switch"
          aria-checked={annual}
          onClick={() => setAnnual((v) => !v)}
        >
          <span className="pm-knob" aria-hidden="true" />
        </button>
        <span className="font-mono text-[0.72rem] text-ink-soft">Annual billing (20% off)</span>
      </div>

      <div className="mt-4 overflow-x-auto">
        <table className="pm-table">
          <thead>
            <tr>
              <th scope="col" aria-label="Feature" />
              {TIERS.map((tier) => (
                <th scope="col" key={tier.name} className={tier.popular ? "popular" : undefined}>
                  <span className="block text-[0.95rem]">{tier.name}</span>
                  <span className="mt-[0.25rem] mb-[0.7rem] block font-mono text-[0.78rem] text-ink-soft">
                    {price(tier.monthly) ?? "Let's talk"}
                  </span>
                  <button
                    type="button"
                    className={
                      tier.kind === "primary"
                        ? "btn-primary"
                        : tier.kind === "ghost"
                          ? "btn-ghost"
                          : "btn-quiet"
                    }
                  >
                    {tier.cta}
                  </button>
                  {tier.popular ? (
                    <span className="mt-[0.5rem] block font-mono text-[0.58rem] uppercase tracking-[0.08em] text-accent">
                      Most popular
                    </span>
                  ) : null}
                </th>
              ))}
            </tr>
          </thead>
          {GROUPS.map((g) => (
            <tbody key={g.group}>
              <tr className="pm-group">
                <th scope="rowgroup" colSpan={4}>
                  {g.group}
                </th>
              </tr>
              {g.rows.map((row) => (
                <tr key={row.label}>
                  <th scope="row">{row.label}</th>
                  {row.cells.map((cell, i) => {
                    const classes = [cell === "—" ? "off" : "", TIERS[i]?.popular ? "pm-pop" : ""]
                      .filter(Boolean)
                      .join(" ");
                    return (
                      <td key={i} className={classes || undefined}>
                        {cell}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          ))}
        </table>
      </div>
    </section>
  );
}
