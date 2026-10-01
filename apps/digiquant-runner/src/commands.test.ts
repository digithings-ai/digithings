// Workers tsconfig types are @cloudflare/workers-types only. This file reads
// wrangler.toml the same way apps/digichat-cloudflare/src/embed-flag.test.ts does.
/// <reference types="node" />
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import commandsJson from "../commands.json";
import {
  assertKnownCommand,
  isArgvStep,
  loadCommands,
  type CommandSpec,
  type CommandStep,
} from "./commands";

function argvOf(step: CommandStep): string[] {
  return isArgvStep(step) ? step : step.argv;
}

const raw = loadCommands(commandsJson);

describe("phase 1 commands", () => {
  it("market-data-refresh argv matches the GHA step", () => {
    const spec = assertKnownCommand("market-data-refresh", raw) as CommandSpec;
    expect(spec.steps[0]).toEqual([
      "uv", "run", "--frozen", "--no-sync", "python",
      "scripts/refresh_market_data_r2.py",
      "--manifest-out", "/tmp/market-data-refresh.json",
    ]);
    expect(spec.timeout_seconds).toBe(1800);
  });

  it("eod fetch-macro is gated on run_writers", () => {
    const spec = assertKnownCommand("prices-eod-macro", raw);
    const gated = spec.steps[1];
    expect(gated).toMatchObject({ when_arg: "run_writers", equals: "true" });
  });

  it("at-open sets the r2 market backend and the ledger flag", () => {
    const spec = assertKnownCommand("prices-at-open", raw);
    expect(spec.market_backend).toBe("r2");
    expect(spec.steps[0]).toContain("--require-ledger");
  });

  it("fx-candles does not call fetch-macro", () => {
    const spec = assertKnownCommand("prices-fx-candles", raw);
    const flat = JSON.stringify(spec.steps);
    expect(flat).not.toContain("fetch-macro");
    expect(flat).toContain("fetch-fx-intraday");
  });

  it("rejects an unknown command", () => {
    expect(() => assertKnownCommand("not-a-command", raw)).toThrow(/unknown command/);
  });

  it("does not declare GitHub failure issues", () => {
    for (const spec of Object.values(raw)) {
      expect(spec).not.toHaveProperty("failure_issue");
    }
  });
});

describe("phase 2 commands", () => {
  it("onchain-bitview matches the Bitview fetch step", () => {
    const spec = assertKnownCommand("onchain-bitview", raw) as CommandSpec;
    expect(spec.timeout_seconds).toBe(900);
    expect(spec.concurrency).toBe("digiquant-onchain");
    expect(spec.code_ref).toBe("main");
    expect(spec.steps).toEqual([[
      "uv", "run", "--frozen", "--no-sync", "python", "-m", "digiquant",
      "onchain", "fetch-bitview",
      "--cache-dir", "data/onchain/bitview",
      "--supabase",
    ]]);
  });

  it("execution-cron-check keeps the five probe steps and no live flags", () => {
    const spec = assertKnownCommand("execution-cron-check", raw);
    expect(spec.timeout_seconds).toBe(600);
    expect(spec.code_ref).toBe("main");
    expect(spec.env).toEqual([
      "CORE_SUPABASE_URL",
      "CORE_SUPABASE_SERVICE_KEY",
      "CLOUDFLARE_EMAIL_API_TOKEN",
      "CLOUDFLARE_ACCOUNT_ID",
      "NOTIFY_FROM",
    ]);
    expect(spec.steps).toHaveLength(5);
    const flat = spec.steps.map((step) => argvOf(step).join(" "));
    expect(flat[0]).toBe(
      "uv run --frozen --no-sync python scripts/execution_cron_check.py",
    );
    expect(flat[1]).toContain("digiquant.dashboard.overlay --dry-run");
    expect(flat[2]).toContain("digiquant.execution.sync_cron --dry-run");
    expect(flat[3]).toContain("digiquant.execution.route_cron --dry-run");
    expect(flat[4]).toContain("digiquant.notify.dispatch --dry-run");
    const blob = flat.join("\n");
    expect(blob).not.toContain("--execute");
    expect(blob).not.toContain("--all");
    expect(blob).not.toContain("portfolio.chain");
    for (const step of spec.steps.slice(1)) {
      expect(isArgvStep(step)).toBe(false);
      if (!isArgvStep(step)) expect(step.always).toBe(true);
    }
  });

  it("research-metrics keeps finalize, verify, refresh, read, attribution", () => {
    const spec = assertKnownCommand("research-metrics", raw);
    expect(spec.timeout_seconds).toBe(1200);
    expect(spec.market_backend).toBe("r2");
    expect(spec.extra_env).toEqual({ DIGIQUANT_ACCOUNTING_FINALIZER: "shadow" });
    const scripts = spec.steps.map((step) => argvOf(step).join(" "));
    expect(scripts.map((line) => line.split(" ").pop())).toEqual([
      "--date",
      "--supabase",
      "--date",
      "--mark-through",
      "--date",
      "--mark-through-book",
      "digiquant/scripts/research/verify_nav_replay.py",
      "--date",
      "digiquant/scripts/research/refresh_attribution.py",
    ]);
    expect(scripts[0]).toContain("finalize_period_accounting.py");
    expect(scripts[1]).toContain("finalize_period_accounting.py");
    expect(scripts[2]).toContain("verify_nav_replay.py --write --date");
    expect(scripts[3]).toContain("verify_nav_replay.py --write --mark-through");
    expect(scripts[4]).toContain("refresh_performance_metrics.py");
    expect(scripts[5]).toContain("--mark-through-book");
    expect(scripts[6]).toBe(
      "uv run --frozen --no-sync python digiquant/scripts/research/verify_nav_replay.py",
    );
    expect(scripts[7]).toContain("refresh_attribution.py --date");
    expect(scripts[8]).toContain("refresh_attribution.py");
    expect(scripts[8]).not.toContain("--date");
    const finalize = spec.steps[1];
    const attribution = spec.steps[8];
    if (isArgvStep(finalize) || isArgvStep(attribution)) {
      throw new Error("date branches must be gated steps");
    }
    expect(finalize.when_arg_empty).toBe("date");
    expect(finalize.continue_on_error).toBe(true);
    expect(attribution.when_arg_empty).toBe("date");
    expect(attribution.always).toBe(true);
    const verifyWrite = spec.steps[3];
    if (isArgvStep(verifyWrite)) throw new Error("mark-through step must be gated");
    expect(verifyWrite.when_arg_empty).toBe("date");
    expect(verifyWrite.append_utc_date).toBe(true);
  });

  it("tearsheets follows calibrations, ccxt fetch, optional macro, generate", () => {
    const spec = assertKnownCommand("tearsheets", raw);
    expect(spec.timeout_seconds).toBe(2700);
    expect(spec.code_ref).toBe("main");
    const lines = spec.steps.map((step) => argvOf(step).join(" "));
    expect(lines[0]).toContain("verify_strategy_calibrations_rls.py");
    expect(lines[1]).toBe(
      "uv run --frozen --with ccxt python digiquant/scripts/fetch_coinbase.py --through-yesterday",
    );
    expect(lines[1]).not.toContain("--no-sync");
    const macro = spec.steps[2];
    if (isArgvStep(macro)) throw new Error("export step must be file-gated");
    expect(macro.when_file).toBe("digiquant/scripts/export_sdca_macro.py");
    expect(lines[3]).toContain("--from-supabase");
    expect(lines[3]).toContain("--push-supabase");
    expect(lines[3]).toContain("--signal-delay-days 3");
    expect(lines[3]).toContain("--cache-dir digiquant/data/price-history");
  });
});

describe("phase 3 house-run", () => {
  it("house-run matches the workflow caps and does not file issues", () => {
    const spec = assertKnownCommand("house-run", raw);
    expect(spec.timeout_seconds).toBe(14400);
    expect(spec.concurrency).toBe("digiquant-pipeline");
    expect(spec.extra_env?.DIGILLM_MAX_CONCURRENT_CALLS).toBe("8");
    expect(spec.extra_env?.DIGIQUANT_SHADOW_ARTIFACT_MODE).toBe("export");
    const flat = JSON.stringify(spec.steps);
    expect(flat).toContain("fetch-macro");
    expect(flat).toContain("fedprob");
    expect(flat).toContain("validate-providers.py");
    expect(flat).toContain("house_chain_step.py");
    expect(spec).not.toHaveProperty("failure_issue");
  });

  it("keeps one standard-2 container class", () => {
    const toml = readFileSync(join(__dirname, "../wrangler.toml"), "utf8");
    const containers = toml.match(/^\[\[containers\]\]/gm) ?? [];
    expect(containers).toHaveLength(1);
    expect(toml).toContain('class_name = "DigiQuantRunnerContainer"');
    expect(toml).toContain('instance_type = "standard-2"');
    expect(toml).toContain("max_instances = 1");
    expect(toml).not.toContain("standard-3");
    expect(toml).not.toContain("standard-4");
    expect(toml).not.toContain("DigiQuantHouseContainer");
  });

  it("allocation-shadow allowlist is empty and the checker is first", () => {
    const spec = assertKnownCommand("allocation-shadow", raw);
    expect(spec.env).toEqual([]);
    expect(spec.alias_supabase).toBeFalsy();
    const first = spec.steps[0];
    const argv = Array.isArray(first) ? first : first.argv;
    expect(argv.join(" ")).toContain("check_allocation_shadow_isolation.py");
    expect(JSON.stringify(spec)).not.toContain("OPENROUTER");
    expect(JSON.stringify(spec)).not.toContain("CORE_SUPABASE");
  });
});

describe("phase 4 checkpoint-archive", () => {
  it("checkpoint-archive matches the workflow and publishes optionally", () => {
    const spec = assertKnownCommand("checkpoint-archive", raw);
    expect(spec.timeout_seconds).toBe(3600);
    expect(spec.concurrency).toBe("checkpoint-archive");
    expect(spec.code_ref).toBe("main");
    expect(spec.alias_supabase).toBe(true);
    expect(spec.env).toEqual([
      "CORE_SUPABASE_URL",
      "CORE_SUPABASE_SERVICE_KEY",
      "R2_ACCOUNT_ID",
      "R2_BUCKET",
      "R2_ACCESS_KEY_ID",
      "R2_SECRET_ACCESS_KEY",
      "CORE_POSTGRES_URI",
    ]);
    const flat = JSON.stringify(spec.steps);
    expect(flat).toContain("digiquant_checkpoint_size_gate.py");
    expect(flat).toContain("--snapshot-out");
    expect(flat).toContain("digiquant_archive_checkpoints.py");
    expect(flat).toContain("--retain-days");
    expect(flat).toContain("--manifest-out");
    expect(spec.steps).toHaveLength(3);
    const size = spec.steps[0];
    const dry = spec.steps[1];
    const live = spec.steps[2];
    if (isArgvStep(size) || isArgvStep(dry) || isArgvStep(live)) {
      throw new Error("checkpoint-archive steps must be gated objects");
    }
    expect(size.continue_on_error).toBe(true);
    expect(size.argv).toContain("/tmp/checkpoint-size-pre.json");
    expect(dry.when_arg).toBe("dry_run");
    expect(dry.equals).toBe("true");
    expect(dry.argv).toContain("--dry-run");
    expect(live.when_arg_empty).toBe("dry_run");
    expect(live.argv).not.toContain("--dry-run");
    expect(spec.publish_if_present).toEqual([
      "/tmp/checkpoint-archive-manifests.json",
      "/tmp/checkpoint-size-pre.json",
    ]);
    expect(spec).not.toHaveProperty("publish");
    expect(spec).not.toHaveProperty("failure_issue");
    expect(JSON.stringify(spec)).not.toContain("GH_ISSUE_TOKEN");
    expect(JSON.stringify(spec)).not.toContain("FRED_API_KEY");
    expect(JSON.stringify(spec)).not.toContain("OPENROUTER_API_KEY");
    expect(JSON.stringify(spec)).not.toContain("LANGSMITH_API_KEY");
  });
});
