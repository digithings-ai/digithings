import { expect, test } from "bun:test";
import { EMPTY_READ, STUB_READ, type ReadResult } from "../read";
import { strategiesBody } from "./strategies-format";

const ok = (lines: string[] = []): ReadResult => ({ status: "ok", lines, asOf: "2026-08-02" });
const NO_DEPLOYMENTS = "No deployments yet.\nno deployment store";

test("a stub, a missed API, and an empty read stay the exact sentence", () => {
  const missed = "/strategies/summary: the official API could not be reached.";
  expect(strategiesBody("st-kpis", null, { status: "error", lines: [missed], asOf: null })).toEqual({
    blocks: [{ kind: "sentence", text: missed }],
  });
  expect(
    strategiesBody(
      "st-catalog",
      { strategies: [{ id: "ema", name: "EMA cross" }] },
      { status: "stub", lines: [STUB_READ], asOf: null },
    ),
  ).toEqual({
    blocks: [{ kind: "sentence", text: STUB_READ }],
  });
  expect(strategiesBody("st-catalog", null, { status: "empty", lines: [EMPTY_READ], asOf: null })).toEqual({
    blocks: [{ kind: "sentence", text: EMPTY_READ }],
  });
  const deployMissed = "/strategies/deployments: the official API could not be reached.";
  expect(
    strategiesBody(
      "st-deployments",
      { deployments: [{ id: "d1", strategy_id: "ema" }] },
      { status: "error", lines: [deployMissed], asOf: null },
    ),
  ).toEqual({
    blocks: [{ kind: "sentence", text: deployMissed }],
  });
});

test("the summary is a stat of the returned fields, or the empty sentence", () => {
  const body = strategiesBody(
    "st-kpis",
    {
      catalog: 2,
      deployable: 1,
      deployments: null,
      paper_accounts: null,
      portfolios: null,
      brokers: null,
      plan: null,
      last_run: "2026-08-02",
      notice: { tag: "soon", text: "Deploy is not built yet." },
      invented: 99,
    },
    ok(["source  core:strategies", "marks  stored"]),
  );
  expect(body.blocks).toEqual([
    { kind: "stat", text: "source  core:strategies   marks  stored" },
    { kind: "stat", text: "catalog  2   deployable  1   last run  2026-08-02" },
    { kind: "sentence", text: "soon  Deploy is not built yet." },
  ]);
  const text = JSON.stringify(body);
  expect(text).not.toContain("invented");
  expect(text).not.toContain("99");
  expect(text).not.toContain("deployments  0");
  expect(text).not.toContain("paper accounts");
  expect(
    strategiesBody(
      "st-kpis",
      {
        catalog: null,
        deployable: null,
        deployments: null,
        paper_accounts: null,
        portfolios: null,
        brokers: null,
        plan: null,
        last_run: null,
        notice: { tag: "soon", text: "Deploy is not built yet." },
      },
      ok(),
    ),
  ).toEqual({ blocks: [{ kind: "sentence", text: EMPTY_READ }] });
});

test("the catalog is a table of returned strategies, or the empty sentence", () => {
  const body = strategiesBody(
    "st-catalog",
    {
      strategies: [
        {
          id: "ema",
          name: "EMA cross",
          family: "nautilus",
          universe: "BTC",
          cadence: null,
          targets: null,
          status: "enabled",
          deploy: null,
          invented: "ghost",
        },
        { id: "", name: "skip", family: "nope", universe: "ETH", cadence: "daily", targets: ["x"], status: "enabled", deploy: "live" },
        { id: "mr", name: "Mean revert", family: null, universe: null, cadence: null, targets: [], status: null, deploy: null },
      ],
    },
    ok(["source  core:strategies"]),
  );
  expect(body.blocks).toEqual([
    { kind: "stat", text: "source  core:strategies" },
    {
      kind: "table",
      columns: ["id", "strategy", "family", "universe", "cadence", "targets", "status", "deploy"],
      rows: [
        ["ema", "EMA cross", "nautilus", "BTC", "—", "—", "enabled", "—"],
        ["mr", "Mean revert", "—", "—", "—", "—", "—", "—"],
      ],
    },
  ]);
  const text = JSON.stringify(body);
  expect(text).not.toContain("ghost");
  expect(text).not.toContain("skip");
  expect(text).not.toContain("daily");
  expect(body.blocks.some((block) => block.kind === "chart")).toBe(false);
  expect(strategiesBody("st-catalog", { strategies: [] }, ok())).toEqual({
    blocks: [{ kind: "sentence", text: EMPTY_READ }],
  });
});

test("deployments are a table, and an empty store stays its empty sentence", () => {
  const body = strategiesBody(
    "st-deployments",
    {
      deployments: [
        { id: "d1", strategy_id: "ema", target: "paper", status: "idle", last_run: "2026-08-01", invented: 4 },
        { id: "", strategy_id: "ghost", target: "live", status: "running", last_run: "2026-08-02" },
        { id: "d2", strategy_id: null, target: null, status: null, last_run: null },
      ],
    },
    ok(["source  core:strategies", "marks  unavailable"]),
  );
  expect(body.blocks).toEqual([
    { kind: "stat", text: "source  core:strategies   marks  unavailable" },
    {
      kind: "table",
      columns: ["deployment", "strategy", "target", "status", "last run"],
      rows: [
        ["d1", "ema", "paper", "idle", "2026-08-01"],
        ["d2", "—", "—", "—", "—"],
      ],
    },
  ]);
  expect(JSON.stringify(body)).not.toContain("ghost");
  expect(JSON.stringify(body)).not.toContain("running");
  expect(strategiesBody("st-deployments", { deployments: [], empty_reason: "no deployment store" }, ok())).toEqual({
    blocks: [{ kind: "sentence", text: NO_DEPLOYMENTS }],
  });
  expect(strategiesBody("st-deployments", null, { status: "empty", lines: [EMPTY_READ], asOf: null })).toEqual({
    blocks: [{ kind: "sentence", text: "No deployments yet." }],
  });
});

test("detail and deploy stay the line read", () => {
  const lines = ["id  ema", "name  EMA cross"];
  const body = strategiesBody("st-overview", { id: "ema", name: "EMA cross", lede: "not this page" }, ok(lines));
  const text = JSON.stringify(body);
  expect(text).toContain("ema");
  expect(text).not.toContain("not this page");
  expect(body.blocks.some((block) => block.kind === "table" && block.columns.includes("strategy"))).toBe(false);
});
