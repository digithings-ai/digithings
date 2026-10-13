/**
 * Job config is read from KV at runtime. This module has no client URL,
 * index name or tenant id. A token never belongs in the config object.
 */

export type CorpusJob = {
  id: string;
  zammadBaseUrl: string;
  siteUrl: string;
  helpIndex: string;
  ticketsIndex: string;
  skipInternal: boolean;
};

const ID = /^[a-z0-9][a-z0-9-]{0,62}$/;
const INDEX = /^[a-z0-9][a-z0-9-]{0,62}$/;

function httpsUrl(value: unknown, field: string): string {
  if (typeof value !== "string") throw new Error(`config_${field}`);
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error(`config_${field}`);
  }
  if (url.protocol !== "https:") throw new Error(`config_${field}`);
  if (url.username || url.password) throw new Error(`config_${field}`);
  return url.origin;
}

function slug(value: unknown, field: string, pattern: RegExp): string {
  if (typeof value !== "string" || !pattern.test(value)) throw new Error(`config_${field}`);
  return value;
}

export function parseJob(raw: unknown): CorpusJob {
  if (typeof raw !== "object" || raw === null) throw new Error("config_job");
  const record = raw as Record<string, unknown>;
  if ("token" in record || "apiToken" in record || "secret" in record) {
    throw new Error("config_secret");
  }
  return {
    id: slug(record.id, "id", ID),
    zammadBaseUrl: httpsUrl(record.zammadBaseUrl, "zammadBaseUrl"),
    siteUrl: httpsUrl(record.siteUrl, "siteUrl"),
    helpIndex: slug(record.helpIndex, "helpIndex", INDEX),
    ticketsIndex: slug(record.ticketsIndex, "ticketsIndex", INDEX),
    skipInternal: record.skipInternal !== false,
  };
}

export function parseJobs(raw: string): CorpusJob[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error("config_jobs");
  }
  if (!Array.isArray(parsed)) throw new Error("config_jobs");
  return parsed.map(parseJob);
}

export const JOBS_KEY = "corpus-index:jobs";
