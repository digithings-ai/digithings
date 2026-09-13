"use client";
/**
 * Dev-only SDCA research "tier sheet" (not in the published PUBLISHED map).
 *
 * Renders every research-trial tearsheet under digiquant/.scratch/tearsheets/
 * (indexed by `digiquant/scripts/build_candidates_tier_sheet.py`) through the
 * same <StrategyLibrary/> grid the live /strategies page uses, so candidates
 * can be sorted/filtered/compared with the same fidelity as production
 * strategies — without writing to settings.json, presets, or Supabase.
 *
 * Fetched from /preview-tearsheets/_candidates_index.json, the same
 * public/preview-tearsheets symlink into digiquant/.scratch/tearsheets/ used
 * by the single-tearsheet preview page. Each card links to
 * /strategies/preview/?file=<trial-id> rather than the live per-strategy
 * route. Only useful under `npm run dev`.
 */
import { useEffect, useState } from "react";
import { SiteNav } from "@/components/landing/SiteNav";
import { AmbientMesh } from "@/components/landing/AmbientMesh";
import { StrategyLibrary } from "@/components/tearsheet/strategy-library";
import type { StrategyIndexEntry } from "@/components/tearsheet/types";

export default function CandidatesTierSheetPage() {
  const [entries, setEntries] = useState<StrategyIndexEntry[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetch("/preview-tearsheets/_candidates_index.json", { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
        return res.json();
      })
      .then((json) => {
        if (alive) setEntries(json as StrategyIndexEntry[]);
      })
      .catch((e: unknown) => {
        if (alive) {
          setErr(
            "Could not load _candidates_index.json from .scratch/tearsheets/ — " +
              `did you run scripts/build_candidates_tier_sheet.py? ` +
              `(${e instanceof Error ? e.message : String(e)})`,
          );
        }
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <>
      <SiteNav />
      <main className="dq-subpage pb-[clamp(4.5rem,10vw,7rem)]">
        <AmbientMesh />
        <div className="wrap pb-[1.5rem]">
          <header className="dq-sechead">
            <div className="kicker">{"// research"}</div>
            <h1 className="dq-title">Candidate tier sheet</h1>
            <p className="dq-sub">
              Local SDCA research trials from .scratch/tearsheets/ — sortable and filterable like
              the live library. None of these are published; none are in settings.json.
            </p>
          </header>
          {err ? (
            <p className="ts-status">{err}</p>
          ) : !entries ? (
            <p className="ts-status">Loading candidates…</p>
          ) : (
            <StrategyLibrary strategies={entries} />
          )}
        </div>
      </main>
    </>
  );
}
