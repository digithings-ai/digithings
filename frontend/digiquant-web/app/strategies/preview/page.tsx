"use client";
/**
 * Dev-only SDCA research-loop preview (not in the published PUBLISHED map).
 *
 * Renders the real <TearsheetView/> component against a local JSON file
 * produced by `digiquant/scripts/emit_sdca_trial_tearsheet.py`, so a research
 * trial gets the same equity-curve/fills/DCA-overlay view as production
 * without touching settings.json, presets, or Supabase.
 *
 * Fetched from /preview-tearsheets/<file>.json, a symlink (public/preview-
 * tearsheets) into digiquant/.scratch/tearsheets/ — only populated by the
 * emit script, never committed. Only useful under `npm run dev`.
 */
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { SiteNav } from "@/components/landing/SiteNav";
import { TearsheetView } from "@/components/tearsheet/tearsheet-view";
import type { TearsheetData } from "@/components/tearsheet/types";

function PreviewContent() {
  const searchParams = useSearchParams();
  const file = searchParams.get("file");
  const [data, setData] = useState<TearsheetData | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!file) return;
    let alive = true;
    setData(null);
    setErr(null);
    fetch(`/preview-tearsheets/${file}.json`, { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
        return res.json();
      })
      .then((json) => {
        if (alive) setData(json as TearsheetData);
      })
      .catch((e: unknown) => {
        if (alive) {
          setErr(
            `Could not load ${file}.json from .scratch/tearsheets/ — ` +
              `did you run emit_sdca_trial_tearsheet.py --trial-id ${file}? ` +
              `(${e instanceof Error ? e.message : String(e)})`,
          );
        }
      });
    return () => {
      alive = false;
    };
  }, [file]);

  if (!file) {
    return (
      <p className="ts-status">
        Open with <code>?file=&lt;trial-id&gt;</code> naming a JSON emitted by{" "}
        <code>emit_sdca_trial_tearsheet.py</code>.
      </p>
    );
  }
  if (err) return <p className="ts-status">{err}</p>;
  if (!data) return <p className="ts-status">Loading {file}…</p>;
  return <TearsheetView key={file} slug={file} data={data} />;
}

export default function StrategyPreviewPage() {
  return (
    <>
      <SiteNav />
      <main className="ts-page dq-subpage">
        <div className="wrap">
          <Suspense fallback={<p className="ts-status">Loading…</p>}>
            <PreviewContent />
          </Suspense>
        </div>
      </main>
    </>
  );
}
