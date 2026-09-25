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

type Round = { slug: string; caption: string };
type Section = { title: string; description?: string; rounds: Round[] };

const SECTIONS: Section[] = [
  {
    title: "Ablation rounds 1–4 and 8",
    rounds: [
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
    ],
  },
  {
    title: "Validated baseline vs. live production",
    description:
      "The candidate RESEARCH_STATE.md calls best (+84.90% OOS, 2026-09-03) vs. what's actually deployed in settings.json right now — and a fresh, less-rosy re-score of that same validated baseline surfaced during this comparison pass.",
    rounds: [
      {
        slug: "btc_sdca_validated_baseline",
        caption: "RESEARCH_STATE.md's canonical +84.90% OOS candidate — but a fresher rescore under a refreshed walk-forward split puts it at only +13.78% mean OOS with 1 of 3 folds infeasible. See its tearsheet notes for the full caveat.",
      },
      {
        slug: "btc_sdca_live_settings",
        caption: "What's live in settings.json right now (same curve, +2 extra weekly weights vs. the validated baseline) — -34.80% mean OOS, loses outright. Validated three times total, losing every time.",
      },
    ],
  },
  {
    title: "Task #93 (2026-09-23) — 17-indicator recalibration, both rounds rejected",
    rounds: [
      {
        slug: "btc_sdca_task93_round2",
        caption: "+4.07% mean OOS, beats the baseline too — but fails the sensitivity-neighbor stability gate (2.79 vs. 2.0 threshold). Not promoted.",
      },
      {
        slug: "btc_sdca_task93_round3",
        caption: "Same weights, feasibility-aware curve search — -2.67% mean OOS. Unambiguous REJECT.",
      },
    ],
  },
  {
    title: "Current live candidate",
    rounds: [
      {
        slug: "btc_sdca",
        caption: "Current live validated candidate — the production BTC-SDCA strategy every round above was tested against.",
      },
    ],
  },
];

const ALL_SLUGS = SECTIONS.flatMap((s) => s.rounds.map((r) => r.slug));

export function SdcaRecalibrationComparison() {
  const [entries, setEntries] = useState<Record<string, StrategyIndexEntry | null> | null>(null);

  useEffect(() => {
    let alive = true;
    void Promise.all(
      ALL_SLUGS.map(async (slug) => {
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
    <div className="flex flex-col gap-8">
      {SECTIONS.map((section) => (
        <div key={section.title} className="flex flex-col gap-3">
          <div>
            <h2
              style={{
                fontFamily: "var(--font-display)",
                fontWeight: 400,
                fontSize: "1.15rem",
                color: "var(--ink)",
                margin: 0,
              }}
            >
              {section.title}
            </h2>
            {section.description ? (
              <p className="dq-sub" style={{ marginTop: "0.3rem", marginBottom: 0 }}>
                {section.description}
              </p>
            ) : null}
          </div>
          <div className="ts-lib-grid">
            {section.rounds.map(({ slug, caption }) => {
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
        </div>
      ))}
    </div>
  );
}
