/**
 * Study D's invoice: the same 1GB RAG agent at 1k queries/day, priced four
 * ways. Review-only — it sits under the traditional-stack walk on
 * `/variants/why-copy` so the price thread can be read next to the lock-in
 * drawing. Every figure comes out of `ragCost()` (dated Sep-2026 list
 * prices); nothing here is hardcoded, so a rate change updates the panel by
 * itself. Planning estimates, not quotes — the footnote says so.
 *
 * Server component. Provider marks come from the kit's logo registry where
 * it has them (OpenAI); the rest render as monogram chips, which is the
 * honest read — those vendors publish no single-path monochrome mark.
 */

import { StackRow } from "@digithings/ui";

import {
  DEFAULT_WORKLOAD,
  RAG_PRICING,
  RAG_STATES,
  ragCost,
  scaleWorkload,
} from "@/lib/ragCost";

const LABEL = "font-mono text-[0.68rem] uppercase tracking-[0.08em] text-ink-mute";
const CELL = "border border-hair px-[0.9rem] py-[0.7rem] font-mono text-[0.82rem] text-ink";
const HEAD = "border border-hair bg-surface px-[0.9rem] py-[0.7rem] font-mono text-[0.68rem] uppercase tracking-[0.08em] text-ink-mute";
const NUM = "text-right font-variant-numeric tabular-nums";

function usd(n: number): string {
  return n === 0 ? "$0" : `$${n.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

export function RagCostPanel() {
  const meta = RAG_STATES.map(({ id, label, note }) => {
    const once = ragCost(id, DEFAULT_WORKLOAD);
    const ten = ragCost(id, scaleWorkload(DEFAULT_WORKLOAD, 10));
    return { label, note, setup: once.setup, monthly: once.monthly, scaled: ten.monthly };
  });
  return (
    <div className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[1rem] px-[var(--page-pad)] pb-[2.5rem]">
      <span className={LABEL}>study D · the invoice</span>
      <p className="m-0 max-w-[var(--measure-prose)] text-[0.9rem] leading-[1.7] text-ink-soft">
        The same agent — 1GB of text, a thousand answers a day — priced four ways. The
        provider column is all metered; the digithings columns move the same workload
        down the price ladder, state by state.
      </p>
      <div className="flex flex-col gap-[0.4rem]">
        <span className={LABEL}>who bills you on the provider stack</span>
        <StackRow
          items={[
            { name: "OpenAI", icon: "openai" },
            { name: "Pinecone", icon: null, mono: "Pc" },
            { name: "LangSmith", icon: null, mono: "LS" },
          ]}
          className="stack-row"
        />
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className={HEAD}>setup</th>
              <th className={`${HEAD} ${NUM}`}>setup</th>
              <th className={`${HEAD} ${NUM}`}>monthly · 1×</th>
              <th className={`${HEAD} ${NUM}`}>monthly · 10×</th>
            </tr>
          </thead>
          <tbody>
            {meta.map((row) => (
              <tr key={row.label}>
                <td className={CELL}>
                  {row.label}
                  <span className="block text-[0.72rem] text-ink-mute">{row.note}</span>
                </td>
                <td className={`${CELL} ${NUM}`}>{usd(row.setup)}</td>
                <td className={`${CELL} ${NUM}`}>{usd(row.monthly)}</td>
                <td className={`${CELL} ${NUM}`}>{usd(row.scaled)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="m-0 max-w-[var(--measure-prose)] font-mono text-[0.72rem] leading-[1.7] text-ink-mute">
        List prices researched {RAG_PRICING.researchedAt}; planning estimates, not quotes.
        Assumes 1GB ≈ 250M tokens in 500-token chunks, 8k in / 1.5k out per answer.
        Self-hosted is $0 marginal on hardware you already pay for — never free.
      </p>
    </div>
  );
}
