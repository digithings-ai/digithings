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

test("the tearsheet stays the line read", () => {
  const sheet = strategiesBody(
    "st-tearsheet",
    { label: "EMA", equity_curve: [{ t: "2024-01-01", v: 1 }, { t: "2024-02-01", v: 2 }] },
    ok(["label  EMA"]),
  );
  const sheetText = JSON.stringify(sheet);
  expect(sheetText).toContain("EMA");
  expect(sheet.blocks.some((block) => block.kind === "chart")).toBe(false);
});

test("detail stubs, missed APIs, and an empty read stay the exact sentence", () => {
  const missed = "/strategies/default: the official API could not be reached.";
  expect(strategiesBody("st-overview", { id: "ema", name: "EMA cross" }, { status: "error", lines: [missed], asOf: null })).toEqual({
    blocks: [{ kind: "sentence", text: missed }],
  });
  expect(
    strategiesBody(
      "st-parameters",
      { parameters: [{ name: "fast", value: 12, state: null }] },
      { status: "stub", lines: [STUB_READ], asOf: null },
    ),
  ).toEqual({ blocks: [{ kind: "sentence", text: STUB_READ }] });
  expect(strategiesBody("st-runs", null, { status: "empty", lines: [EMPTY_READ], asOf: null })).toEqual({
    blocks: [{ kind: "sentence", text: EMPTY_READ }],
  });
  const trackMissed = "/strategies/default/performance: the official API could not be reached.";
  expect(
    strategiesBody(
      "st-track-record",
      { available: true, points: [{ date: "2026-01-01", value: 1 }, { date: "2026-01-02", value: 2 }] },
      { status: "error", lines: [trackMissed], asOf: null },
    ),
  ).toEqual({ blocks: [{ kind: "sentence", text: trackMissed }] });
});

test("overview fields are a stat, or a table when more than four are present", () => {
  const stat = strategiesBody(
    "st-overview",
    {
      id: "ema",
      name: "EMA cross",
      lede: null,
      family: "nautilus",
      universe: "BTC",
      cadence: null,
      targets: null,
      related_thesis: null,
      execution: null,
      invented: "ghost",
    },
    ok(["source  core:strategies"]),
  );
  expect(stat.blocks).toEqual([
    { kind: "stat", text: "source  core:strategies" },
    { kind: "stat", text: "id  ema   name  EMA cross   family  nautilus   universe  BTC" },
  ]);
  expect(JSON.stringify(stat)).not.toContain("ghost");
  expect(JSON.stringify(stat)).not.toContain("cadence");

  const table = strategiesBody(
    "st-overview",
    {
      id: "ema",
      name: "EMA cross",
      lede: "crosses",
      family: "nautilus",
      universe: "BTC",
      cadence: null,
      targets: ["paper"],
      related_thesis: null,
      execution: null,
    },
    ok(),
  );
  expect(table.blocks).toEqual([
    {
      kind: "table",
      columns: ["field", "value"],
      rows: [
        ["id", "ema"],
        ["name", "EMA cross"],
        ["lede", "crosses"],
        ["family", "nautilus"],
        ["universe", "BTC"],
        ["targets", "paper"],
      ],
    },
  ]);
  expect(
    strategiesBody(
      "st-overview",
      {
        id: null,
        name: null,
        lede: null,
        family: null,
        universe: null,
        cadence: null,
        targets: [],
        related_thesis: null,
        execution: null,
      },
      ok(),
    ),
  ).toEqual({ blocks: [{ kind: "sentence", text: EMPTY_READ }] });
});

test("parameters are a table, and an empty store stays its empty sentence", () => {
  const body = strategiesBody(
    "st-parameters",
    {
      parameters: [
        { name: "fast", value: 12, state: null, invented: "nope" },
        { name: "", value: 99, state: "skip" },
        { name: "slow", value: "true", state: "unparsed" },
      ],
    },
    ok(["source  core:strategies", "marks  stored"]),
  );
  expect(body.blocks).toEqual([
    { kind: "stat", text: "source  core:strategies   marks  stored" },
    {
      kind: "table",
      columns: ["name", "value", "state"],
      rows: [
        ["fast", "12", "—"],
        ["slow", "true", "unparsed"],
      ],
    },
  ]);
  expect(JSON.stringify(body)).not.toContain("99");
  expect(JSON.stringify(body)).not.toContain("nope");
  expect(strategiesBody("st-parameters", { parameters: [] }, ok())).toEqual({
    blocks: [{ kind: "sentence", text: "No parameters." }],
  });
  expect(strategiesBody("st-parameters", { parameters: [], empty_reason: "no strategy" }, ok())).toEqual({
    blocks: [{ kind: "sentence", text: "No parameters.\nno strategy" }],
  });
});

test("the track record is a card stat and a point table, with a chart only for two numeric values", () => {
  const one = strategiesBody(
    "st-track-record",
    {
      available: true,
      reason: null,
      points: [{ date: "2026-01-01", value: 10, nav: 99 }],
      card: { name: "EMA cross", symbol: null, net_profit_pct: 1.2 },
    },
    ok(),
  );
  expect(one.blocks.some((block) => block.kind === "chart")).toBe(false);
  expect(one.blocks.map((block) => block.kind)).toEqual(["stat", "table"]);
  expect(JSON.stringify(one)).not.toContain("99");
  expect(JSON.stringify(one)).not.toContain(EMPTY_READ);

  const missing = strategiesBody(
    "st-track-record",
    {
      available: true,
      reason: null,
      points: [
        { date: "2026-01-01", value: null, nav: 10 },
        { date: "2026-01-02", value: null, nav: 30 },
      ],
      card: null,
    },
    ok(),
  );
  expect(missing.blocks.some((block) => block.kind === "chart")).toBe(false);
  expect(missing.blocks).toEqual([
    {
      kind: "table",
      columns: ["date", "value"],
      rows: [
        ["2026-01-01", "—"],
        ["2026-01-02", "—"],
      ],
    },
  ]);
  expect(JSON.stringify(missing)).not.toContain("10");
  expect(JSON.stringify(missing)).not.toContain("30");

  const two = strategiesBody(
    "st-track-record",
    {
      available: true,
      reason: null,
      points: [
        { date: "2026-01-01", value: 10 },
        { date: "2026-01-02", value: 30 },
      ],
      card: { name: "EMA cross", symbol: "BTC", net_profit_pct: null, invented: 7 },
    },
    ok(["source  core:strategy_tearsheets"]),
  );
  expect(two.blocks.map((block) => block.kind)).toEqual(["stat", "stat", "chart", "table"]);
  expect(two.blocks[1]).toEqual({ kind: "stat", text: "name  EMA cross   symbol  BTC" });
  expect(two.blocks[2]).toEqual({ kind: "chart", text: "▁█" });
  expect(JSON.stringify(two)).not.toContain("invented");
  expect(JSON.stringify(two)).not.toContain(EMPTY_READ);

  const flat = strategiesBody(
    "st-track-record",
    {
      available: true,
      reason: null,
      points: [
        { date: "2026-01-01", value: 5 },
        { date: "2026-01-02", value: 5 },
      ],
      card: null,
    },
    ok(),
  );
  expect(flat.blocks[0]).toEqual({ kind: "chart", text: "▄▄" });

  expect(
    strategiesBody("st-track-record", { available: false, reason: "no strategy", points: [], card: null }, ok()),
  ).toEqual({ blocks: [{ kind: "sentence", text: "Not available.\nno strategy" }] });
  expect(
    strategiesBody(
      "st-track-record",
      { available: false, reason: "tearsheet has no dated curve", points: [], card: { name: "EMA cross", kind: null } },
      ok(["marks  unavailable"]),
    ).blocks,
  ).toEqual([
    { kind: "stat", text: "marks  unavailable" },
    { kind: "stat", text: "name  EMA cross" },
    { kind: "sentence", text: "Not available.\ntearsheet has no dated curve" },
  ]);
});

test("runs are a table, and an empty store stays its empty sentence", () => {
  const body = strategiesBody(
    "st-runs",
    {
      runs: [
        { run_date: "2026-08-01", deployment_id: "d1", status: "idle", invented: 4 },
        { run_date: "", deployment_id: "ghost", status: "running" },
        { run_date: "2026-08-02", deployment_id: null, status: null },
      ],
    },
    ok(["source  core:strategies"]),
  );
  expect(body.blocks).toEqual([
    { kind: "stat", text: "source  core:strategies" },
    {
      kind: "table",
      columns: ["run", "deployment", "status"],
      rows: [
        ["2026-08-01", "d1", "idle"],
        ["2026-08-02", "—", "—"],
      ],
    },
  ]);
  expect(JSON.stringify(body)).not.toContain("ghost");
  expect(JSON.stringify(body)).not.toContain("running");
  expect(strategiesBody("st-runs", { runs: [], empty_reason: "no deployment store" }, ok())).toEqual({
    blocks: [{ kind: "sentence", text: "No runs.\nno deployment store" }],
  });
  expect(strategiesBody("st-runs", { runs: [] }, ok())).toEqual({
    blocks: [{ kind: "sentence", text: "No runs." }],
  });
});

test("deploy stubs, missed APIs, and an empty read stay the exact sentence", () => {
  const missed = "/strategies/targets: the official API could not be reached.";
  expect(
    strategiesBody(
      "st-targets",
      { targets: [{ target: "paper", description: "Paper only" }] },
      { status: "error", lines: [missed], asOf: null },
    ),
  ).toEqual({ blocks: [{ kind: "sentence", text: missed }] });
  expect(
    strategiesBody(
      "st-deploy-flow",
      { steps: [{ label: "Confirm", detail: "No order is sent.", state: "todo", status: "soon" }] },
      { status: "stub", lines: [STUB_READ], asOf: null },
    ),
  ).toEqual({ blocks: [{ kind: "sentence", text: STUB_READ }] });
  expect(strategiesBody("st-deploy-draft", null, { status: "empty", lines: [EMPTY_READ], asOf: null })).toEqual({
    blocks: [{ kind: "sentence", text: EMPTY_READ }],
  });
});

test("targets are a table, and an empty list stays its empty sentence", () => {
  const body = strategiesBody(
    "st-targets",
    {
      targets: [
        { target: "paper", description: "Paper only", status: "soon", order: 3 },
        { target: "", description: "skip", status: "live" },
        { target: "broker", description: null, status: null },
      ],
    },
    ok(["source  core:strategies", "marks  unavailable"]),
  );
  expect(body.blocks).toEqual([
    { kind: "stat", text: "source  core:strategies   marks  unavailable" },
    {
      kind: "table",
      columns: ["target", "what it is", "status"],
      rows: [
        ["paper", "Paper only", "soon"],
        ["broker", "—", "—"],
      ],
    },
  ]);
  const text = JSON.stringify(body);
  expect(text).not.toContain("skip");
  expect(text).not.toContain("live");
  expect(text).not.toContain("order");
  expect(body.blocks.some((block) => block.kind === "chart")).toBe(false);
  expect(strategiesBody("st-targets", { targets: [], empty_reason: "no deployment store" }, ok())).toEqual({
    blocks: [{ kind: "sentence", text: "No targets.\nno deployment store" }],
  });
  expect(strategiesBody("st-targets", { targets: [] }, ok())).toEqual({
    blocks: [{ kind: "sentence", text: "No targets." }],
  });
  expect(strategiesBody("st-targets", null, { status: "empty", lines: [EMPTY_READ], asOf: null })).toEqual({
    blocks: [{ kind: "sentence", text: EMPTY_READ }],
  });
});

test("plan steps are a table, and an empty list stays its empty sentence", () => {
  const body = strategiesBody(
    "st-deploy-flow",
    {
      steps: [
        { label: "Choose a target", detail: "Paper only.", state: "todo", status: "soon", qty: 9 },
        { label: "", detail: "skip", state: "done", status: "live" },
        { label: "Confirm", detail: "No order is sent.", state: null, status: null },
      ],
    },
    ok(["source  static:deploy-flow"]),
  );
  expect(body.blocks).toEqual([
    { kind: "stat", text: "source  static:deploy-flow" },
    {
      kind: "table",
      columns: ["step", "state", "status", "detail"],
      rows: [
        ["Choose a target", "todo", "soon", "Paper only."],
        ["Confirm", "—", "—", "No order is sent."],
      ],
    },
  ]);
  expect(JSON.stringify(body)).not.toContain("skip");
  expect(JSON.stringify(body)).not.toContain("9");
  expect(strategiesBody("st-deploy-flow", { steps: [], empty_reason: "no plan" }, ok())).toEqual({
    blocks: [{ kind: "sentence", text: "No deploy steps.\nno plan" }],
  });
  expect(strategiesBody("st-deploy-flow", { steps: [] }, ok())).toEqual({
    blocks: [{ kind: "sentence", text: "No deploy steps." }],
  });
});

test("draft fields are a stat or a table, and a draft is not an order", () => {
  const few = strategiesBody(
    "st-deploy-draft",
    {
      target_kind: "paper",
      paper_capital: null,
      broker: null,
      portfolio: "house",
      schedule: null,
      notice: { tag: "soon", text: "Deploy is not built yet." },
      order: { id: "o1", qty: 10 },
    },
    ok(["source  static:deploy-draft", "marks  unavailable"]),
  );
  expect(few.blocks).toEqual([
    { kind: "stat", text: "source  static:deploy-draft   marks  unavailable" },
    { kind: "sentence", text: "soon  Deploy is not built yet." },
    { kind: "stat", text: "target kind  paper   portfolio  house" },
  ]);
  const fewText = JSON.stringify(few);
  expect(fewText).not.toContain("o1");
  expect(fewText).not.toContain("qty");
  expect(fewText).not.toContain("order");
  expect(few.blocks.some((block) => block.kind === "chart")).toBe(false);

  const many = strategiesBody(
    "st-deploy-draft",
    {
      target_kind: "paper",
      paper_capital: "10000",
      broker: "none",
      portfolio: "house",
      schedule: "daily",
    },
    ok(),
  );
  expect(many.blocks).toEqual([
    {
      kind: "table",
      columns: ["field", "value"],
      rows: [
        ["target kind", "paper"],
        ["paper capital", "10000"],
        ["broker", "none"],
        ["portfolio", "house"],
        ["schedule", "daily"],
      ],
    },
  ]);

  expect(
    strategiesBody(
      "st-deploy-draft",
      {
        target_kind: null,
        paper_capital: null,
        broker: null,
        portfolio: null,
        schedule: null,
        notice: { tag: "soon", text: "Deploy is not built yet." },
      },
      ok(),
    ),
  ).toEqual({ blocks: [{ kind: "sentence", text: "soon  Deploy is not built yet." }] });
  expect(
    strategiesBody(
      "st-deploy-draft",
      { target_kind: null, paper_capital: null, broker: null, portfolio: null, schedule: null },
      ok(),
    ),
  ).toEqual({ blocks: [{ kind: "sentence", text: EMPTY_READ }] });
});
