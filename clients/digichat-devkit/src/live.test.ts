import { expect, test } from "bun:test";
import {
  activateStrip,
  blankDraft,
  chatBody,
  cycleChoice,
  cycleModel,
  enumOptions,
  interpretBaseline,
  liveFrom,
  mainChrome,
  postBaseline,
  rowsFor,
  stripRows,
  toggleFlag,
  toggleTool,
  typeInto,
  type Draft,
  type SettingRow,
  type StripRow,
} from "./live";
import { fieldKey, panesFor } from "./present";
import { interpretResponse, loadKit, type KitRead } from "./read";

const acme = interpretResponse({
  entries: [
    {
      id: "file:config/acme.yaml",
      kind: "file",
      label: "config/acme.yaml",
      ok: true,
      issues: ["accent contrast"],
      redactedText: "slug: acme\n# the server never sends this line\n",
      deployment: {
        slug: "acme",
        persistence: "memory",
        auth: "anonymous",
        backend: { type: "digigraph", apiKeyEnv: "sk-live-secret" },
        chrome: {
          skin: "digichat",
          theme: "dark",
          placeholder: "Ask",
          title: "Acme",
          welcome: { title: "Hello", body: ["Line one"] },
          suggestions: ["Status"],
        },
        features: { attachments: false, pageContext: "off" },
        models: { default: "house", available: ["house", "other"] },
        gate: { mode: "ungated", consumeUrl: "https://secret.example/quota" },
        tools: { allowUserToggle: true, catalog: [{ id: "vault", label: "vault", default: true }] },
        mcp: { servers: [{ id: "docs", url: "https://mcp.example/docs" }] },
      },
    },
  ],
});

function painted(read: KitRead, draft = blankDraft()): string {
  const view = liveFrom(read, draft);
  return JSON.stringify({ panes: panesFor(read, draft), view, rows: rowsFor(read, draft) });
}

test("a down read renders an empty live app and invents no thread", async () => {
  const down = await loadKit("http://127.0.0.1:9", AbortSignal.timeout(800));
  const view = liveFrom(down, blankDraft());
  expect(view.configured).toBe(false);
  expect(view.headline).toBe("—");
  expect(view.modelLine).toBe("—");
  expect(view.placeholder).toBeNull();
  expect(view.welcomeTitle).toBeNull();
  expect(view.suggestions).toEqual([]);
  expect(view.tools).toEqual([]);
  expect(view.mcp).toEqual([]);
  expect(rowsFor(down, blankDraft()).filter((row) => row.kind === "group").map((row) => row.text)).toEqual([
    "Deployments",
    "Basics",
    "Appearance",
    "Advanced",
    "Export",
    "Validation",
  ]);
  const titles = rowsFor(down, blankDraft())
    .filter((row) => row.kind === "head")
    .map((row) => row.text);
  expect(titles).toContain("Tools");
  expect(titles).toContain("MCP servers");
  expect(titles).toContain("Gate");
  expect(painted(down)).not.toContain("demo");
  expect(painted(down)).not.toContain("session-");
  const body = chatBody(view, [], "hi", "u1");
  expect(body.messages).toEqual([{ id: "u1", role: "user", parts: [{ type: "text", text: "hi" }] }]);
  expect(body.model).toBeUndefined();
  expect(body.tools).toBeUndefined();
  const chrome = mainChrome(view, down.detail, []);
  expect(chrome.map((row) => row.slot)).toEqual(["title", "headline", "welcome", "welcome", "thread"]);
  expect(chrome.map((row) => row.text)).toEqual(["—", "—", "—", "—", "configs unreachable"]);
  expect(JSON.stringify(chrome)).not.toContain("What should we inspect");
});

test("the selected deployment configures the live app", () => {
  const view = liveFrom(acme, blankDraft());
  expect(view.headline).toBe("acme · digichat · dark");
  expect(view.title).toBe("Acme");
  expect(view.placeholder).toBe("Ask");
  expect(view.welcomeTitle).toBe("Hello");
  expect(view.welcomeBody).toBe("Line one");
  expect(view.suggestions).toEqual(["Status"]);
  expect(view.modelLine).toBe("house");
  expect(view.activeModel).toBe("house");
  expect(view.gate).toBe("ungated");
  expect(view.tools).toEqual([{ id: "vault", label: "vault", on: true }]);
  expect(view.mcp).toEqual([{ id: "docs", url: "https://mcp.example/docs", on: true }]);
  expect(view.issues).toEqual(["accent contrast"]);
  expect(view.attachments).toBe(false);
  expect(mainChrome(view, acme.detail, []).map((row) => row.text)).toEqual([
    "Acme",
    "acme · digichat · dark",
    "Hello",
    "Line one",
    "",
  ]);
});

test("editing a setting updates the live app and a secret never lands in the draft", () => {
  let draft = typeInto(blankDraft(), fieldKey("appearance", "composer placeholder"), "Ask", false, "!");
  expect(liveFrom(acme, draft).placeholder).toBe("Ask!");
  draft = toggleFlag(draft, fieldKey("features", "attachments"), "off");
  expect(liveFrom(acme, draft).attachments).toBe(true);
  draft = toggleTool(draft, "vault", true);
  expect(liveFrom(acme, draft).tools[0]?.on).toBe(false);
  const secretKey = fieldKey("gate", "quota consume URL (server-side)");
  let sealed = blankDraft();
  for (const ch of "https://secret.example/quota") {
    sealed = typeInto(sealed, secretKey, "set", true, ch);
  }
  expect(sealed.values).toEqual({});
  const leaked = {
    ...blankDraft(),
    values: { [secretKey]: "https://secret.example/injected" },
  };
  const text = painted(acme, leaked);
  expect(text).not.toContain("secret.example");
  expect(text).not.toContain("sk-live-secret");
  // The export paints the draft from the structured deployment, so "slug: acme"
  // is now on screen by design. What must stay out is the redacted file body
  // the server declined to send.
  expect(text).toContain("slug: acme");
  expect(text).not.toContain("the server never sends this line");
});

test("a send carries the draft model, tools, and mcp and drops system notes", () => {
  const view = liveFrom(acme, blankDraft());
  const body = chatBody(
    view,
    [
      { id: "u0", role: "user", text: "earlier" },
      { id: "e0", role: "system", text: "baseline unreachable" },
    ],
    "hi",
    "u1",
  );
  expect(body.model).toBe("house");
  expect(body.tools).toEqual([{ id: "vault", enabled: true }]);
  expect(body.mcp).toEqual([{ id: "docs", url: "https://mcp.example/docs" }]);
  expect(body.messages).toEqual([
    { id: "u0", role: "user", parts: [{ type: "text", text: "earlier" }] },
    { id: "u1", role: "user", parts: [{ type: "text", text: "hi" }] },
  ]);
  expect(JSON.stringify(body)).not.toContain("secret.example");
  expect(JSON.stringify(body)).not.toContain("sk-live-secret");
  const off = toggleTool(blankDraft(), "vault", true);
  expect(chatBody(liveFrom(acme, off), [], "hi", "u1").tools).toEqual([{ id: "vault", enabled: false }]);
});

test("cycling a model and toggling a tool are the strip actions", () => {
  const view = liveFrom(acme, blankDraft());
  const rows = stripRows(view);
  const model = rows.find((row) => row.kind === "model");
  if (!model || model.kind !== "model") throw new Error("missing model row");
  const cycled = activateStrip(blankDraft(), model, view);
  expect(cycled.model).toBe("other");
  expect(liveFrom(acme, cycled).modelLine).toBe("other");
  expect(liveFrom(acme, cycled).activeModel).toBe("other");
  const tool = rows.find((row) => row.kind === "tool");
  if (!tool) throw new Error("missing tool row");
  const toggled = activateStrip(blankDraft(), tool, view);
  expect(liveFrom(acme, toggled).tools[0]?.on).toBe(false);
  const empty = stripRows(liveFrom(interpretResponse({ entries: [] }), blankDraft()));
  expect(empty.find((row) => row.kind === "empty" && row.slot === "tools")?.text).toBe("none");
  expect(cycleModel(blankDraft(), [], null)).toEqual(blankDraft());
});

test("every enum pane field is a choice, not free text", () => {
  const enumed: Array<[string, string]> = [
    ["appearance", "skin"],
    ["appearance", "theme"],
    ["appearance", "mode"],
    ["appearance", "user bubble alignment"],
    ["features", "page context"],
    ["backend", "backend type"],
    ["backend", "persistence"],
    ["backend", "auth"],
    ["gate", "mode"],
    ["gate", "activity detail"],
    ["gate", "LLM access"],
    ["gate", "minimum plan tier"],
  ];
  for (const [pane, label] of enumed) {
    const choices = enumOptions(pane, label);
    expect(choices === null ? null : Array.isArray(choices)).toBe(true);
    expect(choices?.length ?? 0).toBeGreaterThan(1);
  }
  // A text field and a secret field are NOT choices: they keep the free-text editor.
  expect(enumOptions("appearance", "title")).toBeNull();
  expect(enumOptions("appearance", "welcome title")).toBeNull();
  expect(enumOptions("gate", "quota consume URL (server-side)")).toBeNull();
  expect(enumOptions("appearance", "attribution credit")).toBeNull();
  // Option lists are the schema's, in schema order, with the catalog default first.
  expect(enumOptions("appearance", "theme")).toEqual(["dark", "light"]);
  expect(enumOptions("appearance", "mode")).toEqual(["app", "embed", "modal", "sidebar"]);
  expect(enumOptions("gate", "mode")).toEqual(["turn_limited", "ungated", "trial_form"]);
  expect(enumOptions("backend", "backend type")).toEqual([
    "digigraph",
    "foundry",
    "openai-completions",
    "openai-responses",
    "anthropic",
    "google-vertex",
    "langgraph",
    "ag-ui",
    "a2a",
  ]);
  expect(enumOptions("appearance", "skin")?.[0]).toBe("base");
  expect(enumOptions("appearance", "skin")).toContain("digichat");
});

test("cycling each enum updates the draft and the strip row", () => {
  const strip = (draft: Draft): Map<string, StripRow> =>
    new Map(
      stripRows(liveFrom(acme, draft), rowsFor(acme, draft))
        .filter((row): row is Extract<StripRow, { kind: "choice" }> => row.kind === "choice")
        .map((row) => [row.key, row]),
    );
  const view = liveFrom(acme, blankDraft());
  const rows = stripRows(view, rowsFor(acme, blankDraft()));
  for (const row of rows) {
    if (row.kind !== "choice") continue;
    const held = blankDraft().values[row.key];
    expect(held).toBeUndefined();
    expect(row.choices.length).toBeGreaterThan(1);
    expect(row.value).not.toBe("");
  }
  // The strip row carries the CURRENT value, so a cycle is measurable from the row alone.
  expect(strip(blankDraft()).get(fieldKey("appearance", "skin"))?.value).toBe("digichat");
  expect(strip(blankDraft()).get(fieldKey("appearance", "theme"))?.value).toBe("dark");
  expect(strip(blankDraft()).get(fieldKey("backend", "backend type"))?.value).toBe("digigraph");
  expect(strip(blankDraft()).get(fieldKey("gate", "mode"))?.value).toBe("ungated");

  const cases: Array<[string, string, string]> = [
    // skin is the LAST catalog skin, so one cycle wraps to the first.
    ["appearance", "skin", "base"],
    ["appearance", "theme", "light"],
    ["appearance", "mode", "app"],
    ["backend", "backend type", "foundry"],
    ["gate", "mode", "trial_form"],
    // This deployment sets no activityDetail, so the pane shows the dash and one
    // cycle lands on the FIRST option rather than staying on an empty value.
    ["gate", "activity detail", "off"],
  ];
  let draft = blankDraft();
  for (const [pane, label, next] of cases) {
    const key = fieldKey(pane, label);
    const row = strip(draft).get(key);
    if (!row || row.kind !== "choice") throw new Error(`missing choice row for ${key}`);
    draft = activateStrip(draft, row, view);
    expect(draft.values[key]).toBe(next);
    // The draft edit is visible in the pane row and in the strip row.
    expect(rowsFor(acme, draft).find((r) => r.kind === "field" && r.pane === pane && r.label === label)?.value).toBe(next);
    expect(strip(draft).get(key)?.value).toBe(next);
  }
  // Cycling twice walks the ring: the held value wins over the row's own displayed
  // value, so passing the same row again advances from where the draft already is.
  const skinKey = fieldKey("appearance", "skin");
  const blankSkin = strip(blankDraft()).get(skinKey);
  if (!blankSkin || blankSkin.kind !== "choice") throw new Error("missing skin row");
  const once = activateStrip(blankDraft(), blankSkin, view);
  const twice = activateStrip(once, blankSkin, view);
  expect(once.values[skinKey]).toBe("base");
  expect(twice.values[skinKey]).toBe("chatgpt");
  // A reverse cycle walks the same ring backwards.
  const theme = strip(blankDraft()).get(fieldKey("appearance", "theme"));
  if (!theme || theme.kind !== "choice") throw new Error("missing theme row");
  expect(cycleChoice(blankDraft(), theme.key, theme.choices, "dark", -1).values[theme.key]).toBe("light");
  expect(cycleChoice(blankDraft(), theme.key, theme.choices, "dark", 2).values[theme.key]).toBe("dark");
  expect(cycleChoice(blankDraft(), theme.key, [], "dark", 1)).toEqual(blankDraft());
  // A value the schema does not offer falls forward to the first option, never to itself.
  expect(cycleChoice(blankDraft(), fieldKey("appearance", "theme"), ["dark", "light"], "neon", 1).values[fieldKey("appearance", "theme")]).toBe("dark");
  // The headline carries the cycled skin and theme.
  expect(liveFrom(acme, draft).headline).toBe("acme · base · light");
});

test("an enum cycle never leaks a secret and never offers one", () => {
  const secretKey = fieldKey("gate", "quota consume URL (server-side)");
  const draft = activateStrip(
    blankDraft(),
    { kind: "choice", key: fieldKey("gate", "mode"), label: "mode", value: "ungated", choices: ["turn_limited", "ungated", "trial_form"] },
    liveFrom(acme, blankDraft()),
  );
  const keys = stripRows(liveFrom(acme, draft), rowsFor(acme, draft)).map((row) => (row.kind === "choice" ? row.key : ""));
  expect(keys).not.toContain(secretKey);
  expect(enumOptions("gate", "quota consume URL (server-side)")).toBeNull();
  const text = painted(acme, draft);
  expect(text).not.toContain("secret.example");
  expect(text).not.toContain("sk-live-secret");
  // A secret outranks an option list. The deployment happens to have no field that is
  // BOTH secret and an enum, so assert the contract on the row itself: without the
  // secret check in stripRows this is a choice row and the assertion fires.
  const secretWithChoices: SettingRow = { kind: "field", pane: "gate", label: "mode", value: "ungated", secret: true };
  expect(stripRows(liveFrom(acme, draft), [secretWithChoices]).some((row) => row.kind === "choice")).toBe(false);
  // And the same field without the secret flag IS a choice, so the row above can only
  // be excluded by its secret flag and not by the field simply lacking options.
  const openWithChoices: SettingRow = { kind: "field", pane: "gate", label: "mode", value: "ungated", secret: false };
  expect(stripRows(liveFrom(acme, draft), [openWithChoices]).some((row) => row.kind === "choice")).toBe(true);
  // The secret field still renders redacted in the side pane, and typing it does nothing.
  const secretRow = rowsFor(acme, draft).find((row) => row.kind === "field" && row.pane === "gate" && row.label === "quota consume URL (server-side)");
  expect(secretRow?.kind === "field" && secretRow.secret).toBe(true);
  expect(typeInto(draft, secretKey, "set", true, "h").values).toEqual({ "gate:mode": "trial_form" });
});

test("strip rows without pane rows keep the strip exactly as it was", () => {
  const view = liveFrom(acme, blankDraft());
  expect(stripRows(view)).toEqual(stripRows(view, []));
  expect(stripRows(view).map((row) => row.kind)).toEqual(["model", "tool", "mcp"]);
  expect(stripRows(view, rowsFor(acme, blankDraft())).map((row) => row.kind)).toEqual([
    "model",
    "choice",
    "choice",
    "choice",
    "choice",
    "choice",
    "choice",
    "choice",
    "choice",
    "choice",
    "choice",
    "choice",
    "choice",
    "tool",
    "mcp",
  ]);
});

test("baseline replies are the streamed text or the error code", () => {
  expect(interpretBaseline(200, 'data: {"type":"text-delta","delta":"Hi"}\n\n', "text/event-stream")).toEqual({
    kind: "text",
    text: "Hi",
  });
  expect(interpretBaseline(502, '{"error":"baseline_upstream_failed","message":"nope"}', "application/json")).toEqual({
    kind: "error",
    detail: "baseline_upstream_failed",
  });
  expect(interpretBaseline(200, "data: {}\n\n", "text/event-stream")).toEqual({
    kind: "error",
    detail: "baseline empty",
  });
  expect(interpretBaseline(404, "", "text/plain")).toEqual({ kind: "error", detail: "baseline 404" });
});

test("an unreachable baseline is an error and not a reply", async () => {
  const result = await postBaseline("http://127.0.0.1:9", { messages: [] }, AbortSignal.timeout(800));
  expect(result).toEqual({ kind: "error", detail: "baseline unreachable" });
});
