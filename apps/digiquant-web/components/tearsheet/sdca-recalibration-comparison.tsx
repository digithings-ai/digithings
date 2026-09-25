"use client";

/**
 * Local-only comparison grid for the SDCA recalibration v1 research arc
 * (#1069 follow-on). Unlike `<StrategyLibraryLive/>`, this fetches a FIXED
 * ordered list of slugs (research rounds + the live baseline) via
 * `fetchTearsheet()` rather than the Supabase-only `fetchStrategyIndex()` —
 * the round1-4/round8 diagnostics are never pushed to Supabase, so they only
 * exist via the static-JSON fallback in `lib/live/strategies.ts`.
 */
import { useEffect, useState } from "react";
import { StrategyCard } from "./strategy-card";
import { type StrategyIndexEntry } from "./types";
import { fetchTearsheet, toIndexEntry } from "@/lib/live/strategies";

const ROUNDS: { slug: string; caption: string }[] = [
  {
    slug: "btc_sdca_round1",
    caption: "-37.31% mean OOS, beats neither bar — hollow win, capital-starved by a too-tight drawdown gate.",
  },
  {
    slug: "btc_sdca_round2",
    caption: "+3.53% mean OOS, clears both bars headline-wise — but fold 2 drawdown breaches 50% and all OOS folds fail the capital-deployed floor.",
  },
  {
    slug: "btc_sdca_round3",
    caption: "+1.91% on a new evaluator (not directly comparable) — fold 2 fixed, fold 1 regressed. Net regression vs. round 2.",
  },
  {
    slug: "btc_sdca_round4",
    caption: "Dead-zone-width sweep re-confirms round 2's shape unchanged. Fold 1 still unsolved; sensitivity not computed.",
  },
  {
    slug: "btc_sdca_round8",
    caption: "Post-mortem reweight (M2-led, no crash override) — beat the baseline but failed the stability gate.",
  },
  {
    slug: "btc_sdca",
    caption: "Current live validated candidate — the production BTC-SDCA strategy these rounds were tested against.",
  },
];

export function SdcaRecalibrationComparison() {
  const [entries, setEntries] = useState<Record<string, StrategyIndexEntry | null> | null>(null);

  useEffect(() => {
    let alive = true;
    void Promise.all(
      ROUNDS.map(async ({ slug }) => {
        const data = await fetchTearsheet(slug);
        return [slug, data ? toIndexEntry(data) : null] as const;
      }),
    ).then((pairs) => {
      if (alive) setEntries(Object.fromEntries(pairs));
    });
    return () => {
      alive = false;
    };
  }, []);

  if (entries === null) {
    return <p className="dq-sub">Loading tearsheets…</p>;
  }

  return (
    <div className="ts-lib-grid">
      {ROUNDS.map(({ slug, caption }) => {
        const e = entries[slug];
        if (!e) {
          return (
            <div key={slug} className="flex flex-col gap-2">
              <p className="dq-sub" style={{ margin: 0 }}>
                {slug}: unavailable (no tearsheet JSON found).
              </p>
            </div>
          );
        }
        return (
          <div key={slug} className="flex flex-col gap-2">
            <StrategyCard e={e} />
            <p
              className="text-[0.78rem] leading-snug"
              style={{ color: "var(--ink-mute)", margin: 0 }}
            >
              {caption}
            </p>
          </div>
        );
      })}
    </div>
  );
}
