"use client";

/**
 * Meters specimen — StepMeter, PlanLadder, Stat and PipelineSelect from
 * @digithings/ui, live. Health states use accent/warn/mute (never up/down,
 * which are P&L colours). All copy below is the specimen's own; the kit
 * hardcodes none.
 */
import { useState } from "react";

import { PipelineSelect, PlanLadder, Stat, StepMeter } from "@digithings/ui/ui";

const PIPELINES = [
  { id: "baseline", label: "Baseline", kind: "baseline" },
  { id: "mine", label: "My pipeline", kind: "user" },
  { id: "fork", label: "Fork of baseline", kind: "fork" },
];

const RUNGS = [
  { id: "free", name: "Free", detail: "Self-hosted defaults", meta: "10 runs" },
  { id: "pro", name: "Pro", detail: "Higher quotas", meta: "100 runs" },
  { id: "team", name: "Team", detail: "Shared workspaces", meta: "1000 runs", locked: true },
];

export function MetersReference() {
  const [pipeline, setPipeline] = useState("baseline");

  return (
    <section className="section-block" id="meters">
      <p className="kicker">{"// meters"}</p>
      <h2 className="title">Usage, plans, one-line KPIs.</h2>
      <p className="section-copy">
        <code>StepMeter</code> turns warn near its limit, <code>PlanLadder</code> marks the current
        rung, <code>Stat</code> is the dense KPI tile with a sparkline slot, and{" "}
        <code>PipelineSelect</code> is a labelled Select that locks when only one option exists.
      </p>

      <div className="mt-[1.2rem] grid gap-[1.2rem] md:grid-cols-2">
        <div className="flex flex-col gap-4 border border-hair p-4">
          <StepMeter label="Runs this month" value={3} limit={10} unit="runs" />
          <StepMeter label="Near limit" value={9} limit={10} unit="runs" />
          <StepMeter label="No data" value={null} limit={10} />
        </div>
        <PlanLadder rungs={RUNGS} current="pro" aria-label="Plan tiers" />
        <div className="grid grid-cols-2 gap-2">
          <Stat label="Holdings" value="24" delta="+2 this week" deltaTone="accent" />
          <Stat label="Coverage" value={null} />
        </div>
        <div className="flex flex-col gap-4 border border-hair p-4">
          <PipelineSelect options={PIPELINES} value={pipeline} onValueChange={setPipeline} />
          <PipelineSelect options={PIPELINES.slice(0, 1)} value="baseline" />
        </div>
      </div>
    </section>
  );
}
