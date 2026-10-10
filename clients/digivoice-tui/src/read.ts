/**
 * digivoice read layer.
 *
 * The digivoice surface has no HTTP API: it is a local Python CLI. Every read
 * here is one `digivoice <cmd>` run through Bun.spawn, parsed from its stdout.
 * The parse functions are pure and are what read.test.ts pins; the spawn is
 * thin and never invented data. A refused or unreachable CLI stays an empty
 * state.
 */
export const DASH = "—";
export const UNREACHABLE = "digivoice could not be reached.";

export type CliResult = { ok: boolean; code: number; stdout: string; stderr: string };

/** The CLI argv prefix. `DIGIVOICE_BIN="python3 -m digivoice"` runs from source. */
export function cliArgv(env: Record<string, string | undefined> = process.env): string[] {
  const raw = (env.DIGIVOICE_BIN ?? "digivoice").trim();
  return raw.length ? raw.split(/\s+/) : ["digivoice"];
}

export async function runCli(args: string[], signal?: AbortSignal): Promise<CliResult> {
  const argv = [...cliArgv(), ...args];
  try {
    const proc = Bun.spawn(argv, { stdin: "ignore", stdout: "pipe", stderr: "pipe", signal });
    const [stdout, stderr, code] = await Promise.all([
      new Response(proc.stdout).text(),
      new Response(proc.stderr).text(),
      proc.exited,
    ]);
    return { ok: code === 0, code, stdout, stderr };
  } catch (error) {
    return { ok: false, code: 127, stdout: "", stderr: error instanceof Error ? error.message : String(error) };
  }
}

function readJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function obj(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function str(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

// --- setup -----------------------------------------------------------------

export type SetupPaths = {
  data_dir: string;
  models_dir: string;
  recordings_dir: string;
  history_file: string;
  settings_file: string;
};
export type Hotkeys = { dict_toggle: string; speak_selection: string; cancel: string };
export type HardwareTier = { tier: string; model: string; note: string };
export type Hardware = { tiers: HardwareTier[]; pointer: string };
export type SetupPayload = {
  settings: Record<string, unknown>;
  paths: SetupPaths;
  hotkeys: Hotkeys;
  presets: Record<string, string>;
  rewrite_model_hint: string;
  setup_menu: string[];
  model_fields: string[];
  feature_fields: string[];
  hardware: Hardware;
};

export function parseSetup(text: string): SetupPayload | null {
  const root = obj(readJson(text));
  if (!root) return null;
  const paths = obj(root.paths) ?? {};
  const hotkeys = obj(root.hotkeys) ?? {};
  const hardware = obj(root.hardware_recommendations) ?? {};
  const tiers = Array.isArray(hardware.tiers)
    ? hardware.tiers
        .map((t) => obj(t))
        .filter((t): t is Record<string, unknown> => t !== null)
        .map((t) => ({ tier: str(t.tier), model: str(t.model), note: str(t.note) }))
    : [];
  const menu = Array.isArray(root.setup_menu) ? root.setup_menu.map((m) => str(m)).filter(Boolean) : [];
  const modelFields = Array.isArray(root.model_fields) ? root.model_fields.map((m) => str(m)).filter(Boolean) : [];
  const featureFields = Array.isArray(root.feature_fields) ? root.feature_fields.map((m) => str(m)).filter(Boolean) : [];
  const presetsRaw = obj(root.presets) ?? {};
  const presets: Record<string, string> = {};
  for (const [k, v] of Object.entries(presetsRaw)) presets[k] = str(v);
  return {
    settings: stripMeta(root),
    paths: {
      data_dir: str(paths.data_dir),
      models_dir: str(paths.models_dir),
      recordings_dir: str(paths.recordings_dir),
      history_file: str(paths.history_file),
      settings_file: str(paths.settings_file),
    },
    hotkeys: {
      dict_toggle: str(hotkeys.dict_toggle),
      speak_selection: str(hotkeys.speak_selection),
      cancel: str(hotkeys.cancel),
    },
    presets,
    rewrite_model_hint: str(root.rewrite_model_hint),
    setup_menu: menu,
    model_fields: modelFields,
    feature_fields: featureFields,
    hardware: { tiers, pointer: str(hardware.pointer) },
  };
}

const META_KEYS = new Set([
  "paths",
  "hotkeys",
  "presets",
  "rewrite_model_hint",
  "setup_menu",
  "model_fields",
  "feature_fields",
  "hardware_recommendations",
]);

function stripMeta(root: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(root)) if (!META_KEYS.has(k)) out[k] = v;
  return out;
}

// --- doctor ----------------------------------------------------------------

export type DoctorStatus = "ok" | "missing" | "info";
export type DoctorCheck = { status: DoctorStatus; id: string; detail: string };
export type DoctorReport = { checks: DoctorCheck[]; ok: boolean };

const DOCTOR_LINE = /^\[(ok|missing|info)\]\s+(\S+)\s*(.*)$/;

export function parseDoctor(text: string): DoctorReport {
  const checks: DoctorCheck[] = [];
  let ok = false;
  for (const line of text.split("\n")) {
    const match = DOCTOR_LINE.exec(line.trim());
    if (match) {
      checks.push({ status: match[1] as DoctorStatus, id: match[2], detail: match[3].trim() });
      continue;
    }
    const result = /^result:\s*(ok|not ready)\s*$/.exec(line.trim());
    if (result) ok = result[1] === "ok";
  }
  return { checks, ok };
}

// --- history ---------------------------------------------------------------

export type HistoryEntry = { ts: string; kind: string; text: string; wav: string | null };
export type History = { file: string; present: boolean; count: number; total: number; entries: HistoryEntry[] };

export function parseHistory(text: string): History {
  const root = obj(readJson(text)) ?? {};
  const entries = Array.isArray(root.entries)
    ? root.entries
        .map((e) => obj(e))
        .filter((e): e is Record<string, unknown> => e !== null)
        .map((e) => ({ ts: str(e.ts), kind: str(e.kind), text: str(e.text), wav: typeof e.wav === "string" ? e.wav : null }))
    : [];
  return {
    file: str(root.file),
    present: root.present === true,
    count: typeof root.count === "number" ? root.count : entries.length,
    total: typeof root.total === "number" ? root.total : entries.length,
    entries,
  };
}

// --- status ----------------------------------------------------------------

export type StatusSnapshot = {
  session: string;
  kind: string;
  state: string;
  text: string;
  detail: string;
  updated_ms: number;
  pid: number | null;
};

export function parseStatus(text: string): StatusSnapshot | null {
  const root = obj(readJson(text));
  if (!root || typeof root.state !== "string") return null;
  return {
    session: str(root.session),
    kind: str(root.kind),
    state: str(root.state),
    text: str(root.text),
    detail: str(root.detail),
    updated_ms: typeof root.updated_ms === "number" ? root.updated_ms : 0,
    pid: typeof root.pid === "number" ? root.pid : null,
  };
}

// --- settings --------------------------------------------------------------

export function parseSettings(text: string): Record<string, unknown> | null {
  return obj(readJson(text));
}

// --- readers ---------------------------------------------------------------

export async function readSetup(signal?: AbortSignal): Promise<SetupPayload | null> {
  const result = await runCli(["setup", "--json"], signal);
  return result.ok ? parseSetup(result.stdout) : null;
}

export async function readDoctor(signal?: AbortSignal): Promise<DoctorReport | null> {
  const result = await runCli(["doctor"], signal);
  // `doctor` exits 1 when the host is not ready; the report is still on stdout.
  const report = parseDoctor(result.stdout);
  return report.checks.length ? report : null;
}

export async function readHistory(signal?: AbortSignal, last?: number): Promise<History | null> {
  const args = ["history", "--json"];
  if (typeof last === "number" && last > 0) args.push("--last", String(last));
  const result = await runCli(args, signal);
  return result.ok ? parseHistory(result.stdout) : null;
}

export async function readStatus(signal?: AbortSignal): Promise<StatusSnapshot | null> {
  const result = await runCli(["status"], signal);
  // No status yet exits 1 with a plain line on stdout; parse returns null then.
  return parseStatus(result.stdout);
}

export async function readSettings(signal?: AbortSignal): Promise<Record<string, unknown> | null> {
  const result = await runCli(["settings", "--json"], signal);
  return result.ok ? parseSettings(result.stdout) : null;
}

export async function saveSetting(key: string, value: string, signal?: AbortSignal): Promise<boolean> {
  const result = await runCli(["settings", "set", key, value], signal);
  return result.ok;
}
