/** Generic tenant recrawl tick. Schedules and targets come from the tenant doc. Dry-run only. */
export type RecrawlTarget = { url: string; store: string; index: string };
export type TenantRecrawl = { cron: string; targets: RecrawlTarget[] };
export type TenantDoc = { recrawl?: TenantRecrawl | null };

export interface TenantDocReader {
  listIds(): Promise<readonly string[]>;
  read(id: string): Promise<TenantDoc | null>;
}

export const EMPTY_TENANT_READER: TenantDocReader = {
  async listIds() {
    return [];
  },
  async read() {
    return null;
  },
};

export type SkipReason = "missing_recrawl" | "empty_targets" | "invalid_cron" | "not_due" | "reader_error";

export type TenantRecrawlTick = {
  dryRun: true;
  ran: { tenantId: string; targets: RecrawlTarget[] }[];
  skipped: { tenantId: string; reason: SkipReason }[];
};

const DOW: Record<string, number> = { sun: 0, mon: 1, tue: 2, wed: 3, thu: 4, fri: 5, sat: 6 };

function num(token: string, min: number, max: number, names?: Record<string, number>): number | null {
  const named = names?.[token.toLowerCase()];
  if (named !== undefined) return named;
  if (!/^\d+$/.test(token)) return null;
  const n = Number(token);
  if (names && n === 7) return 0;
  if (n < min || n > (names ? 7 : max)) return null;
  return n;
}

function field(raw: string, min: number, max: number, names?: Record<string, number>): Set<number> | null {
  if (!raw) return null;
  const values = new Set<number>();
  for (const part of raw.split(",")) {
    const [span, stepRaw, extra] = part.split("/");
    if (!span || extra !== undefined) return null;
    const step = stepRaw === undefined ? 1 : Number(stepRaw);
    if (!Number.isInteger(step) || step < 1) return null;
    if (span !== "*" && !span.includes("-") && stepRaw === undefined) {
      const single = num(span, min, max, names);
      if (single === null) return null;
      values.add(single);
      continue;
    }
    let start = min;
    let end = max;
    if (span !== "*") {
      const [lo, hi, tail] = span.split("-");
      if (!lo || tail !== undefined) return null;
      const a = num(lo, min, max, names);
      const b = hi === undefined ? a : num(hi, min, max, names);
      if (a === null || b === null || a > b) return null;
      start = a;
      end = hi === undefined ? max : b;
    }
    for (let n = start; n <= end; n += step) values.add(n);
  }
  return values.size > 0 ? values : null;
}

function due(expr: string, now: Date): boolean | null {
  const f = expr.trim().split(/\s+/);
  if (f.length !== 5) return null;
  const minute = field(f[0], 0, 59);
  const hour = field(f[1], 0, 23);
  const dom = field(f[2], 1, 31);
  const month = field(f[3], 1, 12);
  const dow = field(f[4], 0, 6, DOW);
  if (!minute || !hour || !dom || !month || !dow) return null;
  if (!minute.has(now.getUTCMinutes()) || !hour.has(now.getUTCHours())) return false;
  if (!month.has(now.getUTCMonth() + 1)) return false;
  const domOk = dom.has(now.getUTCDate());
  const dowOk = dow.has(now.getUTCDay());
  if (f[2] === "*" && f[4] === "*") return true;
  if (f[2] === "*") return dowOk;
  if (f[4] === "*") return domOk;
  return domOk || dowOk;
}

function targetsOf(recrawl: TenantRecrawl): RecrawlTarget[] {
  if (!Array.isArray(recrawl.targets)) return [];
  const out: RecrawlTarget[] = [];
  for (const row of recrawl.targets) {
    if (!row || typeof row.url !== "string" || row.url.length === 0) continue;
    if (typeof row.store !== "string" || row.store.length === 0) continue;
    if (typeof row.index !== "string" || row.index.length === 0) continue;
    out.push({ url: row.url, store: row.store, index: row.index });
  }
  return out;
}

function emit(log: ((fields: Record<string, unknown>) => void) | undefined, fields: Record<string, unknown>): void {
  const line = { event: "tenant-recrawl", ...fields };
  if (log) log(line);
  else console.log(JSON.stringify(line));
}

function detail(err: unknown): string {
  return (err instanceof Error ? err.message : "read_failed").slice(0, 200);
}

export async function runTenantRecrawlTick(opts: {
  now: Date;
  reader: TenantDocReader;
  writer?: { write(target: RecrawlTarget & { tenantId: string }): Promise<void> | void };
  log?: (fields: Record<string, unknown>) => void;
}): Promise<TenantRecrawlTick> {
  const ran: TenantRecrawlTick["ran"] = [];
  const skipped: TenantRecrawlTick["skipped"] = [];
  void opts.writer;

  let ids: readonly string[];
  try {
    ids = await opts.reader.listIds();
  } catch (err) {
    skipped.push({ tenantId: "", reason: "reader_error" });
    emit(opts.log, { tenantId: "", skip: "reader_error", detail: detail(err) });
    return { dryRun: true, ran, skipped };
  }

  for (const tenantId of ids) {
    let doc: TenantDoc | null;
    try {
      doc = await opts.reader.read(tenantId);
    } catch (err) {
      skipped.push({ tenantId, reason: "reader_error" });
      emit(opts.log, { tenantId, skip: "reader_error", detail: detail(err) });
      continue;
    }
    const recrawl = doc?.recrawl;
    if (!recrawl || typeof recrawl !== "object") {
      skipped.push({ tenantId, reason: "missing_recrawl" });
      emit(opts.log, { tenantId, skip: "missing_recrawl" });
      continue;
    }
    const when = typeof recrawl.cron === "string" ? due(recrawl.cron, opts.now) : null;
    if (when === null) {
      skipped.push({ tenantId, reason: "invalid_cron" });
      emit(opts.log, { tenantId, skip: "invalid_cron" });
      continue;
    }
    const targets = targetsOf(recrawl);
    if (targets.length === 0) {
      skipped.push({ tenantId, reason: "empty_targets" });
      emit(opts.log, { tenantId, skip: "empty_targets" });
      continue;
    }
    if (!when) {
      skipped.push({ tenantId, reason: "not_due" });
      continue;
    }
    ran.push({ tenantId, targets });
  }
  return { dryRun: true, ran, skipped };
}
