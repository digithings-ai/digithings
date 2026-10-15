import { expect, test } from "bun:test";
import { panesFor } from "./present";
import { interpretHttp, interpretResponse, loadKit, selectedEntry, type KitRead } from "./read";

const refused = interpretHttp(404, null);
const empty = interpretResponse({ entries: [] });

function values(read: KitRead, id: string): string[] {
  const pane = panesFor(read).find((item) => item.id === id);
  if (!pane) throw new Error(`missing pane ${id}`);
  return pane.lines.map((line) => (line.kind === "field" ? `${line.label}=${line.value}` : line.kind === "mark" ? line.text : line.text));
}

function blob(read: KitRead): string {
  return JSON.stringify(panesFor(read));
}

test("a down service leaves every section empty and invents nothing", async () => {
  const down = await loadKit("http://127.0.0.1:9", AbortSignal.timeout(800));
  expect(down.status).toBe("down");
  expect(down.detail).toBe("configs unreachable");
  expect(refused.detail).toBe("configs 404");
  const panes = panesFor(down);
  expect(panes.map((pane) => pane.title)).toEqual([
    "Deployments",
    "Identity",
    "Features",
    "Models",
    "Appearance",
    "Backend",
    "Tools",
    "MCP servers",
    "Gate",
    "Export",
    "Validation",
  ]);
  expect(values(down, "deployments")).toContain("none");
  expect(values(down, "deployments").filter((line) => line === "none")).toHaveLength(2);
  expect(values(down, "identity")).toEqual(["slug=—", "aliases=—"]);
  expect(values(down, "export")).toEqual([
    "local compose=nothing to export",
    "embed snippet=nothing to export",
    "config YAML=nothing to export",
  ]);
  expect(blob(down)).not.toContain("demo");
  expect(blob(down)).not.toContain("session-");
  expect(selectedEntry(down)).toBeNull();
});

test("an empty catalog is not filled with a sample deployment", () => {
  expect(empty.status).toBe("empty");
  expect(empty.detail).toBe("no deployments");
  expect(values(empty, "tools")).toContain("none");
  expect(values(empty, "mcp")).toContain("none");
  expect(values(empty, "backend")).toEqual(["backend type=—", "persistence=—", "auth=—"]);
  expect(blob(empty)).not.toContain("house");
});

test("a real file fills only the fields it carries", () => {
  const read = interpretResponse({
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
          chrome: { skin: "digichat", theme: "dark", placeholder: "Ask" },
          features: { attachments: false, pageContext: "off" },
          models: { default: "house", available: [] },
          gate: { mode: "ungated", consumeUrl: "https://secret.example/quota" },
          tools: { allowUserToggle: true, catalog: [{ id: "vault", label: "vault", default: true }] },
          mcp: { servers: [] },
        },
      },
      {
        id: "env:other",
        kind: "env",
        label: "other",
        ok: false,
        issues: [],
        redactedText: null,
        deployment: null,
      },
    ],
  });
  expect(read.status).toBe("ok");
  expect(read.detail).toBe("1 local files · 1 environment tenants");
  expect(values(read, "identity")).toEqual(["slug=acme", "aliases=—"]);
  expect(values(read, "features")).toContain("attachments=off");
  expect(values(read, "features")).toContain("dictation=—");
  expect(values(read, "models")).toContain("available models=none");
  expect(values(read, "appearance")).toContain("composer placeholder=Ask");
  expect(values(read, "appearance")).toContain("accent color=—");
  expect(values(read, "backend")).toContain("digisearch index=—");
  expect(values(read, "backend").join(" ")).not.toContain("API key");
  expect(values(read, "gate")).toContain("quota consume URL (server-side)=set");
  expect(values(read, "tools")).toContain("vault=default on");
  expect(values(read, "export")).toContain("config YAML=redacted on file");
  expect(values(read, "validation")).toEqual(["accent contrast"]);
  expect(values(read, "deployments")).toContain("other (invalid)");
  const painted = blob(read);
  expect(painted).not.toContain("sk-live-secret");
  expect(painted).not.toContain("secret.example");
  expect(painted).not.toContain("slug: acme");
});

test("a malformed payload is down rather than a guessed entry", () => {
  const read = interpretResponse({ entries: [{ id: "x" }] });
  expect(read.status).toBe("down");
  expect(read.files).toEqual([]);
});
