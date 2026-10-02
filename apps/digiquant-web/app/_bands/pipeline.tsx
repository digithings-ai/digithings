"use client";

import { useEffect, useState } from "react";
import { Badge } from "@digithings/ui/ui";
import { ExecutionCard, StageCard } from "@/components/pipeline/StageCard";
import { StageRunway } from "@/components/pipeline/StageRunway";
import { officialGet, PIPELINE_ROUTE, runFromDocuments } from "@/lib/official-api";
import type { RunSnapshot } from "@/lib/run-snapshot";
import { Band } from "../_chrome/Band";
import { EXECUTION_STAGE, PIPELINE_STAGES } from "../_stages";

const SOURCE = "dashboard-api GET /v1/tables/documents";

interface RunRead {
  snapshot: RunSnapshot | null;
  reason: string;
}

const READING: RunRead = {
  snapshot: null,
  reason: "Reading the latest run from the official API.",
};

/** The pipeline band. Stage cards plus the latest documents read from the official API. */
export function PipelineBand() {
  const [run, setRun] = useState<RunRead>(READING);

  useEffect(() => {
    let alive = true;
    void (async () => {
      const read = await officialGet(PIPELINE_ROUTE, {
        select: "document_key,title,run_type,date",
        order: "date.desc",
        limit: "1000",
      });
      if (!alive) return;
      if (!read.ok) {
        setRun({ snapshot: null, reason: read.reason });
        return;
      }
      const rows = Array.isArray(read.body) ? read.body : [];
      const snapshot = runFromDocuments(rows);
      setRun({
        snapshot,
        reason: snapshot
          ? `Recorded run ${snapshot.runDate}. The cards above are that capture.`
          : "The official API returned no documents for the latest run.",
      });
    })();
    return () => {
      alive = false;
    };
  }, []);

  const snap = run.snapshot;
  const total = PIPELINE_STAGES.length + 1;
  const badge = snap ? `recorded · ${snap.runDate} · ${snap.runType ?? "run type unknown"}` : "no recorded run";

  return (
    <Band
      id="pipeline"
      fill
      status={snap ? "recorded" : "no recorded run"}
      title="Six stages, one record per run"
      takeaway="A run moves from inputs to learning, and each stage writes down what it did. What you see is a recorded run, not a live one."
    >
      <StageRunway
        label="Pipeline stages"
        intro={
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border border-hair px-3 py-2 font-mono text-[0.68rem] text-ink-mute">
            <span>run</span>
            <Badge variant="neutral">{badge}</Badge>
            <span className="text-ink-soft">
              {snap ? "a recorded run, not live" : "no run was captured for this build; the cards show the pipeline's structure"}
            </span>
            <span className="ms-auto hidden sm:inline">{SOURCE}</span>
          </div>
        }
        outro={
          <p className="m-0 border border-hair px-3 py-2 font-mono text-[0.72rem] leading-[1.55] text-ink-soft">
            {run.reason} Source: {SOURCE}.
          </p>
        }
      >
        {PIPELINE_STAGES.map((name, i) => (
          <li key={name} className="flex min-w-0 snap-start">
            <StageCard
              index={i}
              total={total}
              name={name}
              hasRun={snap !== null}
              recorded={snap?.stages.find((s) => s.name === name)}
            />
          </li>
        ))}
        <li className="flex min-w-0 snap-start">
          <ExecutionCard index={PIPELINE_STAGES.length} total={total} status={EXECUTION_STAGE.status} />
        </li>
      </StageRunway>
    </Band>
  );
}
