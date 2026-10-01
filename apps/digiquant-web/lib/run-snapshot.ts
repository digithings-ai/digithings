import raw from "@/app/_latest-run.json";
import { PIPELINE_STAGES } from "@/app/_stages";

export type StageName = (typeof PIPELINE_STAGES)[number];
export type StageStatus = "recorded" | "not-recorded";

export interface StageSnapshot {
  name: StageName;
  status: StageStatus;
  documentCount: number;
  /** Present only for Inputs / Research / Synthesis. */
  titles?: string[];
}

export interface RunSnapshot {
  runDate: string;
  runType: string | null;
  stages: StageSnapshot[];
}

export interface LatestRunFile {
  capturedAt: string;
  source: string;
  snapshot: RunSnapshot | null;
  reason?: string;
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function parseStage(v: unknown, expected: StageName): StageSnapshot {
  if (!isRecord(v) || v.name !== expected) throw new Error(`_latest-run.json: stage ${expected} missing or out of order`);
  if (v.status !== "recorded" && v.status !== "not-recorded") throw new Error(`_latest-run.json: bad status for ${expected}`);
  if (typeof v.documentCount !== "number" || !Number.isInteger(v.documentCount) || v.documentCount < 0) {
    throw new Error(`_latest-run.json: bad documentCount for ${expected}`);
  }
  const stage: StageSnapshot = { name: expected, status: v.status, documentCount: v.documentCount };
  if (v.titles !== undefined) {
    if (!Array.isArray(v.titles) || !v.titles.every((t) => typeof t === "string")) {
      throw new Error(`_latest-run.json: bad titles for ${expected}`);
    }
    stage.titles = v.titles as string[];
  }
  return stage;
}

/** Validates the committed file's shape; throws at import time if it drifts. */
export function parseLatestRun(input: unknown): LatestRunFile {
  if (!isRecord(input)) throw new Error("_latest-run.json: not an object");
  if (typeof input.capturedAt !== "string" || typeof input.source !== "string") {
    throw new Error("_latest-run.json: capturedAt and source are required");
  }
  const base = { capturedAt: input.capturedAt, source: input.source };
  if (input.snapshot === null) {
    if (typeof input.reason !== "string") throw new Error("_latest-run.json: null snapshot needs a reason");
    return { ...base, snapshot: null, reason: input.reason };
  }
  const s = input.snapshot;
  if (!isRecord(s) || typeof s.runDate !== "string" || !ISO_DATE.test(s.runDate)) {
    throw new Error("_latest-run.json: snapshot.runDate must be YYYY-MM-DD");
  }
  if (s.runType !== null && typeof s.runType !== "string") throw new Error("_latest-run.json: bad runType");
  if (!Array.isArray(s.stages) || s.stages.length !== PIPELINE_STAGES.length) {
    throw new Error("_latest-run.json: stages must match PIPELINE_STAGES");
  }
  const stages = PIPELINE_STAGES.map((name, i) => parseStage((s.stages as unknown[])[i], name));
  return { ...base, snapshot: { runDate: s.runDate, runType: s.runType as string | null, stages } };
}

const latest: LatestRunFile = parseLatestRun(raw);

/** The recorded run, or null when no real run was reachable at capture time. */
export function getSnapshot(): RunSnapshot | null {
  return latest.snapshot;
}

/** Full file including capturedAt, source and, for the empty state, the reason. */
export function getLatestRun(): LatestRunFile {
  return latest;
}
