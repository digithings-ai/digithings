import { describe, expect, test } from "bun:test";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  applySet,
  applySetPath,
  coerce,
  entryMatches,
  fileKeyParts,
  findEntry,
  findKeyLine,
  formatValue,
  interpretConfigs,
  looksTable,
  main,
  parseArgs,
  parseEntry,
  parseMode,
  pathGet,
  pathSet,
  splitPath,
  type CliEntry,
  type FetchLike,
  type Io,
} from "./cli";
import { DASH } from "./read";

const FIXTURE = {
  entries: [
    {
      id: "file:config/datatap-trial-foundry.yaml",
      kind: "file",
      path: "config/datatap-trial-foundry.yaml",
      label: "datatap-trial-foundry",
      readOnly: false,
      ok: true,
      issues: [],
      redactedText:
        "version: 1\n# hand-written look\ndeployment:\n  # the slug names the look\n  slug: datatap-trial-foundry\n  chrome:\n    mode: embed\n    theme: dark\n",
      deployment: { version: 1, slug: "datatap-trial-foundry", chrome: { mode: "embed", theme: "dark" } },
    },
    {
      id: "file:config/examples/digithings-ai-embed.yaml#hosts/digithings.ai",
      kind: "file",
      path: "config/examples/digithings-ai-embed.yaml",
      label: "digithings-ai",
      readOnly: false,
      ok: true,
      issues: [],
      redactedText:
        "version: 1\n# a host-scoped look\nhosts:\n  digithings.ai:\n    slug: digithings-ai\n    chrome:\n      mode: embed\n",
      deployment: { slug: "digithings-ai", chrome: { mode: "embed" } },
    },
    {
      id: "env:app.digithings.ai",
      kind: "env",
      path: null,
      label: "app.digithings.ai",
      readOnly: true,
      ok: true,
      issues: [],
      redactedText: null,
      deployment: { version: 1, slug: "app-digithings" },
    },
    {
      id: "file:config/broken.yaml",
      kind: "file",
      path: "config/broken.yaml",
      label: "broken",
      readOnly: false,
      ok: false,
      issues: ["chrome.mode: invalid enum"],
      redactedText: "version: 1\n",
      deployment: null,
    },
  ],
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function recorder(): { io: Io; out: string[]; err: string[] } {
  const out: string[] = [];
  const err: string[] = [];
  return { io: { out: (line) => out.push(line), err: (line) => err.push(line) }, out, err };
}

function configsFetch(body: unknown = FIXTURE, status = 200): FetchLike {
  return async () => json(body, status);
}

describe("parseEntry / interpretConfigs", () => {
  test("maps the wire shape", () => {
    const entry = parseEntry(FIXTURE.entries[0]);
    expect(entry?.label).toBe("datatap-trial-foundry");
    expect(entry?.text).toContain("mode: embed");
    expect(entry?.readOnly).toBe(false);
  });

  test("env tenants are read-only by kind", () => {
    expect(parseEntry(FIXTURE.entries[2])?.readOnly).toBe(true);
  });

  test("rejects a missing id or label", () => {
    expect(parseEntry({ kind: "file", label: "x" })).toBeNull();
    expect(parseEntry({ id: "file:a.yaml", kind: "file" })).toBeNull();
    expect(parseEntry({ id: "file:a.yaml", kind: "nope", label: "a" })).toBeNull();
  });

  test("a malformed entry makes the whole read unreadable", () => {
    expect(interpretConfigs({ entries: [FIXTURE.entries[0], {}] })).toEqual({
      ok: false,
      detail: "configs unreadable",
    });
    expect(interpretConfigs({ nope: true }).ok).toBe(false);
    expect(interpretConfigs(FIXTURE).ok).toBe(true);
  });
});

describe("entry selection", () => {
  const entries = (interpretConfigs(FIXTURE) as { ok: true; entries: CliEntry[] }).entries;

  test("matches id, label, path and file name", () => {
    const entry = entries[0];
    expect(entryMatches(entry, "file:config/datatap-trial-foundry.yaml")).toBe(true);
    expect(entryMatches(entry, "datatap-trial-foundry")).toBe(true);
    expect(entryMatches(entry, "config/datatap-trial-foundry.yaml")).toBe(true);
    expect(entryMatches(entry, "datatap-trial-foundry.yaml")).toBe(true);
    expect(entryMatches(entry, "nope")).toBe(false);
  });

  test("findEntry returns null when nothing matches", () => {
    expect(findEntry(entries, "datatap-trial-foundry")?.id).toBe("file:config/datatap-trial-foundry.yaml");
    expect(findEntry(entries, "nope")).toBeNull();
  });
});

describe("key paths", () => {
  test("pathGet walks nested mappings", () => {
    expect(pathGet({ chrome: { mode: "embed" } }, "chrome.mode")).toBe("embed");
    expect(pathGet({ chrome: {} }, "chrome.mode")).toBeUndefined();
  });

  test("pathSet creates intermediate mappings and does not mutate the input", () => {
    const before = { chrome: { theme: "dark" } };
    const after = pathSet(before, ["chrome", "mode"], "modal");
    expect(after).toEqual({ chrome: { theme: "dark", mode: "modal" } });
    expect(before).toEqual({ chrome: { theme: "dark" } });
    expect(pathSet(null, splitPath("features.attachments"), true)).toEqual({ features: { attachments: true } });
  });

  test("fileKeyParts wraps a plain look under deployment", () => {
    const entry = parseEntry(FIXTURE.entries[0]) as CliEntry;
    expect(fileKeyParts(entry, "chrome.mode")).toEqual(["deployment", "chrome", "mode"]);
    expect(fileKeyParts(entry, "features.attachments")).toEqual(["deployment", "features", "attachments"]);
  });

  test("fileKeyParts scopes a host look without splitting the host name", () => {
    const entry = parseEntry(FIXTURE.entries[1]) as CliEntry;
    expect(entry.id).toBe("file:config/examples/digithings-ai-embed.yaml#hosts/digithings.ai");
    expect(fileKeyParts(entry, "chrome.mode")).toEqual(["hosts", "digithings.ai", "chrome", "mode"]);
  });

  test("applySetPath replaces one value and keeps every comment", () => {
    const text = "version: 1\n# hand-written look\ndeployment:\n  # the slug names the look\n  slug: datatap-trial-foundry\n  chrome:\n    mode: embed\n    theme: dark # the palette\n";
    const next = applySetPath(text, ["deployment", "chrome", "theme"], "light");
    expect(next).toContain("    theme: light # the palette");
    expect(next).toContain("    mode: embed");
    expect(next).toContain("# hand-written look");
    expect(next).toContain("  # the slug names the look");
  });

  test("applySetPath inserts a missing leaf inside an existing block", () => {
    const text = "deployment:\n  chrome:\n    mode: embed\n";
    const next = applySetPath(text, ["deployment", "chrome", "accent"], "red");
    expect(next).toBe("deployment:\n  chrome:\n    mode: embed\n    accent: red\n");
  });

  test("applySetPath targets a host-scoped deployment under its own host", () => {
    const text = "version: 1\nhosts:\n  digithings.ai:\n    chrome:\n      mode: embed\n  other.ai:\n    chrome:\n      mode: app\n";
    const next = applySetPath(text, ["hosts", "digithings.ai", "chrome", "mode"], "modal");
    expect(next).toContain("      mode: modal");
    expect(next).toContain("  other.ai:\n    chrome:\n      mode: app");
  });

  test("findKeyLine matches a full mapping path, not a substring", () => {
    const lines = "deployment:\n  slug: a\n  chrome:\n    mode: embed\n".replace(/\n$/, "").split("\n");
    expect(findKeyLine(lines, ["deployment", "chrome", "mode"])).toBe(3);
    expect(findKeyLine(lines, ["chrome", "mode"])).toBe(-1);
  });

  test("applySet keeps the preserved-secret sentinel", () => {
    const text = "version: 1\nbackend:\n  apiKeyEnv: __DEVKIT_PRESERVED__\nchrome:\n  mode: embed\n";
    const next = applySet(text, "chrome.mode", "modal");
    expect(next).toContain("mode: modal");
    expect(next).toContain("apiKeyEnv: __DEVKIT_PRESERVED__");
    expect(next).toContain("version: 1");
  });
});

describe("mode aliases", () => {
  test("maps the ticket names onto the schema enum", () => {
    expect(parseMode("fullscreen")).toBe("app");
    expect(parseMode("popup")).toBe("modal");
    expect(parseMode("embedded")).toBe("embed");
    expect(parseMode("sidebar")).toBe("sidebar");
    expect(parseMode("EMBED")).toBe("embed");
    expect(parseMode("diagonal")).toBeNull();
  });
});

describe("value coercion", () => {
  test("types scalars, lists and objects", () => {
    expect(coerce("true")).toBe(true);
    expect(coerce("false")).toBe(false);
    expect(coerce("42")).toBe(42);
    expect(coerce("1.5")).toBe(1.5);
    expect(coerce('["a","b"]')).toEqual(["a", "b"]);
    expect(coerce('{"a":1}')).toEqual({ a: 1 });
    expect(coerce("digichat")).toBe("digichat");
  });

  test("formats values for the terminal", () => {
    expect(formatValue(undefined)).toBe(DASH);
    expect(formatValue("dark")).toBe("dark");
    expect(formatValue(false)).toBe("false");
    expect(formatValue([1, 2])).toContain("1");
  });
});

describe("looksTable", () => {
  test("lists labels, kind and state", () => {
    const entries = (interpretConfigs(FIXTURE) as { ok: true; entries: CliEntry[] }).entries;
    const table = looksTable(entries);
    expect(table).toContain("datatap-trial-foundry");
    expect(table).toContain("read-only");
    expect(table).toContain("invalid: chrome.mode: invalid enum");
  });
});

describe("parseArgs", () => {
  test("splits command, positionals and flags", () => {
    expect(parseArgs(["set", "look", "chrome.mode", "modal"])).toEqual({
      command: "set",
      args: ["look", "chrome.mode", "modal"],
      flags: {},
    });
    expect(parseArgs(["looks", "--url", "http://x", "--json"]).flags).toEqual({
      url: "http://x",
      json: true,
    });
    expect(parseArgs(["get", "look", "--url=http://y"]).flags.url).toBe("http://y");
    expect(parseArgs([]).command).toBe("help");
  });
});

describe("main", () => {
  test("looks prints the table and exits 0", async () => {
    const { io, out } = recorder();
    expect(await main(["looks"], io, configsFetch())).toBe(0);
    expect(out.join("\n")).toContain("datatap-trial-foundry");
  });

  test("get reads one key and export prints the YAML", async () => {
    const first = recorder();
    expect(await main(["get", "datatap-trial-foundry", "chrome.mode"], first.io, configsFetch())).toBe(0);
    expect(first.out[0]).toBe("embed");

    const second = recorder();
    expect(await main(["export", "datatap-trial-foundry"], second.io, configsFetch())).toBe(0);
    expect(second.out[0]).toContain("slug: datatap-trial-foundry");
  });

  test("set posts the mutated YAML to the save route", async () => {
    let posted: { id?: string; text?: string } = {};
    const ff: FetchLike = async (url, init) => {
      if (url.endsWith("/api/devkit/configs")) return json(FIXTURE);
      posted = JSON.parse(String(init?.body)) as { id?: string; text?: string };
      return json({ ok: true, backup: "config/datatap-trial-foundry.yaml.bak" });
    };
    const { io, out } = recorder();
    expect(await main(["set", "datatap-trial-foundry", "chrome.theme", "light"], io, ff)).toBe(0);
    expect(posted.id).toBe("file:config/datatap-trial-foundry.yaml");
    expect(posted.text).toContain("theme: light");
    expect(posted.text).toContain("mode: embed");
    // the look is hand-written: comments must survive the edit
    expect(posted.text).toContain("# hand-written look");
    expect(posted.text).toContain("# the slug names the look");
    expect(out[0]).toContain("backup");
  });

  test("set on a host-scoped look edits only its own host block", async () => {
    let posted: { id?: string; text?: string } = {};
    const ff: FetchLike = async (url, init) => {
      if (url.endsWith("/api/devkit/configs")) return json(FIXTURE);
      posted = JSON.parse(String(init?.body)) as { id?: string; text?: string };
      return json({ ok: true });
    };
    const { io, out } = recorder();
    expect(await main(["set", "digithings-ai", "chrome.mode", "modal"], io, ff)).toBe(0);
    expect(posted.id).toBe("file:config/examples/digithings-ai-embed.yaml#hosts/digithings.ai");
    expect(posted.text).toContain("      mode: modal");
    expect(posted.text).toContain("  digithings.ai:");
    expect(out[0]).toBe("set digithings-ai chrome.mode = modal");
  });

  test("mode maps fullscreen to the app enum value", async () => {
    let text = "";
    const ff: FetchLike = async (url, init) => {
      if (url.endsWith("/api/devkit/configs")) return json(FIXTURE);
      text = (JSON.parse(String(init?.body)) as { text: string }).text;
      return json({ ok: true });
    };
    const { io } = recorder();
    expect(await main(["mode", "datatap-trial-foundry", "fullscreen"], io, ff)).toBe(0);
    expect(text).toContain("mode: app");
  });

  test("refuses to write an environment tenant", async () => {
    const { io, err } = recorder();
    expect(await main(["set", "app.digithings.ai", "chrome.mode", "modal"], io, configsFetch())).toBe(1);
    expect(err[0]).toContain("read-only");
  });

  test("reports an unknown look and a dead service", async () => {
    const miss = recorder();
    expect(await main(["get", "ghost"], miss.io, configsFetch())).toBe(1);
    expect(miss.err[0]).toContain("no look matches");

    const down = recorder();
    const ff: FetchLike = async () => {
      throw new Error("ECONNREFUSED");
    };
    expect(await main(["looks"], down.io, ff)).toBe(1);
    expect(down.err[0]).toContain("unreachable");
  });

  test("surfaces save validation issues", async () => {
    const { io, err } = recorder();
    const ff: FetchLike = async (url) => {
      if (url.endsWith("/api/devkit/configs")) return json(FIXTURE);
      return json({ ok: false, issues: ["chrome.mode: invalid enum"] }, 422);
    };
    expect(await main(["set", "datatap-trial-foundry", "chrome.mode", "nope"], io, ff)).toBe(1);
    expect(err[0]).toContain("invalid enum");
  });

  test("imports a file into a look", async () => {
    const file = join(tmpdir(), `digichat-devkit-cli-${Date.now()}.yaml`);
    await Bun.write(file, "version: 1\nslug: datatap-trial-foundry\n");
    let posted: { id?: string; text?: string } = {};
    const ff: FetchLike = async (url, init) => {
      if (url.endsWith("/api/devkit/configs")) return json(FIXTURE);
      posted = JSON.parse(String(init?.body)) as { id?: string; text?: string };
      return json({ ok: true });
    };
    const { io } = recorder();
    expect(await main(["import", "datatap-trial-foundry", file], io, ff)).toBe(0);
    expect(posted.id).toBe("file:config/datatap-trial-foundry.yaml");
    expect(posted.text).toContain("version: 1");
    await Bun.file(file).delete();
  });

  test("validate reports ok and failure", async () => {
    const ok = recorder();
    const okFetch: FetchLike = async () => json({ ok: true });
    const file = join(tmpdir(), `digichat-devkit-cli-ok-${Date.now()}.yaml`);
    await Bun.write(file, "version: 1\n");
    expect(await main(["validate", file], ok.io, okFetch)).toBe(0);
    expect(ok.out[0]).toBe("ok");

    const bad = recorder();
    const badFetch: FetchLike = async () => json({ ok: false, issues: ["chrome.mode: invalid enum"] }, 422);
    expect(await main(["validate", file], bad.io, badFetch)).toBe(1);
    expect(bad.err[0]).toContain("invalid enum");
    await Bun.file(file).delete();
  });

  test("unknown command exits 2 with help", async () => {
    const { io, err } = recorder();
    expect(await main(["wat"], io, configsFetch())).toBe(2);
    expect(err[0]).toContain("unknown command");
  });
});
