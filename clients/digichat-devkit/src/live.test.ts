import { expect, test } from "bun:test";
import {
  activateStrip,
  blankDraft,
  chatBody,
  cycleModel,
  interpretBaseline,
  liveFrom,
  mainChrome,
  postBaseline,
  rowsFor,
  stripRows,
  toggleFlag,
  toggleTool,
  typeInto,
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
      redactedText: "slug: acme\n",
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
  expect(text).not.toContain("slug: acme");
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
