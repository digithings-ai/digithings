import { describe, expect, it } from "vitest";
import commandsJson from "../commands.json";
import { assertKnownCommand, loadCommands, type CommandSpec } from "./commands";

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
    expect(() => assertKnownCommand("house-run", raw)).toThrow(/unknown command/);
  });
});
