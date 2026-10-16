import { describe, expect, it } from "vitest";
import {
  appendListItem,
  applyAll,
  createDraft,
  createNewFileDraft,
  deleteKey,
  deleteListItemField,
  DEVKIT_SENTINEL,
  formatYamlScalar,
  isDirty,
  isValidSlug,
  removeListItem,
  secretState,
  secretStateInList,
  setBoolean,
  setListItemScalar,
  setScalar,
  setStringList,
  setWelcomeTitle,
  withText,
  withValidation,
} from "./draft";
import { DEVKIT_SENTINEL as SERVER_SENTINEL } from "@/lib/devkit-configs";

const FIXTURE = `version: 1
deployment:
  slug: demo-chat
  chrome:
    mode: embed
    theme: light
    skin: digichat
    title: Demo chat
    suggestions:
      - What can you do?
      - Search my workspace
  persistence: none
  auth: anonymous
  features:
    attachments: true
    dictation: false
  models:
    available: []
  backend:
    type: digigraph
  gate:
    mode: ungated
`;

const HOSTS_FIXTURE = `version: 1
deployment:
  slug: primary
  chrome:
    theme: light
hosts:
  example.com:
    slug: example-host
    chrome:
      theme: dark
  other.com:
    slug: other-host
    chrome:
      theme: light
`;

const SENTINEL_FIXTURE = `version: 1
deployment:
  slug: secret-chat
  chrome:
    theme: dark
  backend:
    type: digigraph
  token: __DEVKIT_PRESERVED__
  gate:
    mode: ungated
    consumeUrl: __DEVKIT_PRESERVED__
`;

describe("draft state", () => {
  it("starts clean and tracks dirty transitions", () => {
    const d = createDraft({ entryId: "file:a.yaml", scope: ["deployment"], savedText: FIXTURE, parsed: null });
    expect(isDirty(d)).toBe(false);
    expect(isDirty(withText(d, `${FIXTURE}\n`))).toBe(true);
    // Round-trip back to saved text clears dirty.
    expect(isDirty(withText(d, FIXTURE))).toBe(false);
  });

  it("withValidation refreshes issues but keeps last-valid parsed", () => {
    const parsed = { slug: "demo-chat" } as never;
    const d = createDraft({ entryId: "file:a.yaml", scope: ["deployment"], savedText: FIXTURE, parsed });
    const invalid = withValidation(d, { issues: ["boom"], deployment: null });
    expect(invalid.issues).toEqual(["boom"]);
    expect(invalid.parsed).toBe(parsed);
    const next = { slug: "demo-chat-2" } as never;
    const valid = withValidation(invalid, { issues: [], deployment: next });
    expect(valid.issues).toEqual([]);
    expect(valid.parsed).toBe(next);
  });

  it("new-file drafts carry no entry and start clean (m1)", () => {
    const d = createNewFileDraft();
    expect(d.entryId).toBeNull();
    expect(d.scope).toEqual(["deployment"]);
    expect(isDirty(d)).toBe(false);
    expect(isDirty(withText(d, `${d.text}# touch\n`))).toBe(true);
    expect(d.text).toContain("slug: new-deployment");
    // The template seeds a backend block so the Backend type switch can
    // rebuild in place (no parent key → the helper would refuse).
    expect(d.text).toContain("backend:\n    type: digigraph");
  });
});

describe("isValidSlug", () => {
  it("accepts lowercase slugs, rejects the rest", () => {
    expect(isValidSlug("demo-chat-2")).toBe(true);
    expect(isValidSlug("Demo")).toBe(false);
    expect(isValidSlug("has space")).toBe(false);
    expect(isValidSlug("has_underscore")).toBe(false);
    expect(isValidSlug("")).toBe(false);
  });
});

describe("setScalar", () => {
  it("replaces an existing scalar, preserving the rest of the file", () => {
    const r = setScalar(FIXTURE, ["deployment"], ["chrome", "theme"], "dark");
    expect(r.applied).toBe(true);
    expect(r.text).toContain("    theme: dark");
    expect(r.text).not.toContain("theme: light");
    expect(r.text).toContain("  slug: demo-chat");
  });

  it("scopes edits to the hosts sub-entry, not the top-level deployment", () => {
    const r = setScalar(HOSTS_FIXTURE, ["hosts", "example.com"], ["chrome", "theme"], "light");
    expect(r.applied).toBe(true);
    const otherBlock = r.text.slice(r.text.indexOf("other.com:"));
    expect(otherBlock).toContain("theme: light");
    expect(r.text).toContain("  slug: primary");
  });

  it("inserts a missing key after the parent header", () => {
    const r = setScalar(FIXTURE, ["deployment"], ["chrome", "placeholder"], "Ask me");
    expect(r.applied).toBe(true);
    expect(r.text).toContain("    placeholder: Ask me");
  });

  it("creates a missing intermediate map", () => {
    const bare = "version: 1\ndeployment:\n  slug: demo\n";
    const r = setScalar(bare, ["deployment"], ["chrome", "theme"], "dark");
    expect(r.applied).toBe(true);
    expect(r.text).toContain("  chrome:\n    theme: dark");
  });

  it("refuses when the key owns block content", () => {
    const r = setScalar(FIXTURE, ["deployment"], ["chrome"], "flat");
    expect(r.applied).toBe(false);
    expect(r.text).toBe(FIXTURE);
  });

  it("refuses on unknown scope and empty key paths", () => {
    expect(setScalar(FIXTURE, ["nope"], ["theme"], "dark").applied).toBe(false);
    expect(setScalar(FIXTURE, ["deployment"], [], "dark").applied).toBe(false);
    expect(setScalar(FIXTURE, ["deployment"], [], "dark").text).toBe(FIXTURE);
  });

  it("round-trips through a scalar that needs quoting", () => {
    const r = setScalar(FIXTURE, ["deployment"], ["chrome", "title"], "Ask: anything?");
    expect(r.applied).toBe(true);
    expect(r.text).toContain('    title: "Ask: anything?"');
  });
});

describe("setWelcomeTitle", () => {
  const STRING_WELCOME = `version: 1
deployment:
  slug: demo-chat
  chrome:
    mode: embed
    welcome: Ask about your pipelines.
  backend:
    type: digigraph
`;
  const MAP_WELCOME = `version: 1
deployment:
  slug: demo-chat
  chrome:
    mode: embed
    welcome:
      title: Old title
      body: Old body
  backend:
    type: digigraph
`;

  it("replaces a scalar welcome string with a title map", () => {
    const r = setWelcomeTitle(STRING_WELCOME, ["deployment"], "New title");
    expect(r.applied).toBe(true);
    expect(r.text).toContain("    welcome:\n      title: New title");
    expect(r.text).not.toContain("Ask about your pipelines.");
    expect(r.text).toContain("  backend:\n    type: digigraph");
  });

  it("sets the nested title when welcome is already a map (body kept)", () => {
    const r = setWelcomeTitle(MAP_WELCOME, ["deployment"], "New title");
    expect(r.applied).toBe(true);
    expect(r.text).toContain("      title: New title");
    expect(r.text).toContain("      body: Old body");
  });

  it("creates the welcome map when absent", () => {
    const bare = "version: 1\ndeployment:\n  slug: demo\n  chrome:\n    mode: embed\n";
    const r = setWelcomeTitle(bare, ["deployment"], "Hello");
    expect(r.applied).toBe(true);
    expect(r.text).toContain("    welcome:\n      title: Hello");
  });
});

describe("setBoolean", () => {
  it("renders true/false and rejects non-booleans", () => {
    const r = setBoolean(FIXTURE, ["deployment"], ["features", "dictation"], true);
    expect(r.applied).toBe(true);
    expect(r.text).toContain("    dictation: true");
    const bad = setBoolean(FIXTURE, ["deployment"], ["features", "dictation"], "yes" as never);
    expect(bad.applied).toBe(false);
    expect(bad.text).toBe(FIXTURE);
  });
});

describe("setStringList", () => {
  it("replaces existing items", () => {
    const r = setStringList(FIXTURE, ["deployment"], ["chrome", "suggestions"], ["One", "Two"]);
    expect(r.applied).toBe(true);
    expect(r.text).toContain("    suggestions:\n      - One\n      - Two");
    expect(r.text).not.toContain("What can you do?");
  });

  it("converts an inline empty list into a block", () => {
    const r = setStringList(FIXTURE, ["deployment"], ["models", "available"], ["gpt-x"]);
    expect(r.applied).toBe(true);
    expect(r.text).toContain("    available:\n      - gpt-x");
  });

  it("renders an empty list inline", () => {
    const r = setStringList(FIXTURE, ["deployment"], ["chrome", "suggestions"], []);
    expect(r.applied).toBe(true);
    expect(r.text).toContain("    suggestions: []");
    expect(r.text).not.toContain("- What can you do?");
  });

  it("inserts a missing list after the parent header", () => {
    const r = setStringList(FIXTURE, ["deployment"], ["aliases"], ["a", "b"]);
    expect(r.applied).toBe(true);
    expect(r.text).toContain("  aliases:\n    - a\n    - b");
  });

  it("refuses when the key owns a nested map", () => {
    const r = setStringList(FIXTURE, ["deployment"], ["chrome"], ["x"]);
    expect(r.applied).toBe(false);
    expect(r.text).toBe(FIXTURE);
  });

  it("refuses a list with block-scalar items instead of orphaning continuations (M1)", () => {
    const text = [
      "version: 1",
      "deployment:",
      "  slug: blocky",
      "  backend:",
      "    type: digigraph",
      "  chrome:",
      "    suggestions:",
      "      - |",
      "        multi-line",
      "        prompt",
      "      - plain",
      "",
    ].join("\n");
    const r = setStringList(text, ["deployment"], ["chrome", "suggestions"], ["New"]);
    expect(r.applied).toBe(false);
    expect(r.text).toBe(text);
  });

  it("refuses clearing a list with block-scalar items", () => {
    const text = [
      "version: 1",
      "deployment:",
      "  slug: blocky",
      "  backend:",
      "    type: digigraph",
      "  chrome:",
      "    suggestions:",
      "      - |",
      "        multi-line",
      "",
    ].join("\n");
    const r = setStringList(text, ["deployment"], ["chrome", "suggestions"], []);
    expect(r.applied).toBe(false);
    expect(r.text).toBe(text);
  });
});

describe("formatYamlScalar", () => {
  it("quotes only when YAML would misread the value", () => {
    expect(formatYamlScalar("plain value 123")).toBe("plain value 123");
    expect(formatYamlScalar("true")).toBe('"true"');
    expect(formatYamlScalar("007")).toBe('"007"');
    expect(formatYamlScalar("a: b")).toBe('"a: b"');
    expect(formatYamlScalar("")).toBe('""');
    expect(formatYamlScalar('say "hi"')).toBe('"say \\"hi\\""');
  });
});

describe("sentinel passthrough", () => {
  it("leaves secret sentinel lines byte-identical", () => {
    const r = setScalar(SENTINEL_FIXTURE, ["deployment"], ["chrome", "theme"], "light");
    expect(r.applied).toBe(true);
    expect(r.text).toContain("  token: __DEVKIT_PRESERVED__");
    expect(r.text).toContain("    consumeUrl: __DEVKIT_PRESERVED__");
    // Only the theme line changed.
    const before = SENTINEL_FIXTURE.split("\n");
    const after = r.text.split("\n");
    expect(after.length).toBe(before.length);
    const changed = before.filter((line, i) => line !== after[i]);
    expect(changed).toEqual(["    theme: dark"]);
  });
});

describe("client sentinel constant", () => {
  it("matches the server redaction sentinel", () => {
    expect(DEVKIT_SENTINEL).toBe(SERVER_SENTINEL);
  });
});

const LIST_FIXTURE = `version: 1
deployment:
  slug: demo-chat
  tools:
    allowUserToggle: true
    catalog:
      - id: web_search
        label: Web search
        default: true
      - id: calculator
        label: Calculator
  mcp:
    allowUserServers: false
    servers:
      - id: digisearch
        url: https://search.internal/mcp
        label: Digisearch
        token: __DEVKIT_PRESERVED__
`;

describe("deleteKey", () => {
  it("removes a scalar line", () => {
    const r = deleteKey(FIXTURE, ["deployment"], ["chrome", "title"]);
    expect(r.applied).toBe(true);
    expect(r.text).not.toContain("title: Demo chat");
    expect(r.text).toContain("skin: digichat");
  });
  it("removes a nested map with its block", () => {
    const r = deleteKey(FIXTURE, ["deployment"], ["chrome"]);
    expect(r.applied).toBe(true);
    expect(r.text).not.toContain("skin:");
    expect(r.text).toContain("persistence: none");
  });
  it("is a no-op (applied false) when the key is absent", () => {
    const r = deleteKey(FIXTURE, ["deployment"], ["chrome", "accent"]);
    expect(r).toEqual({ text: FIXTURE, applied: false });
  });
  it("refuses a missing scope", () => {
    expect(deleteKey(FIXTURE, ["nope"], ["a"]).applied).toBe(false);
  });
});

describe("setListItemScalar", () => {
  it("edits a dash-inline field", () => {
    const r = setListItemScalar(LIST_FIXTURE, ["deployment"], ["tools", "catalog"], 1, "id", "math");
    expect(r.applied).toBe(true);
    expect(r.text).toContain("- id: math");
    expect(r.text).toContain("- id: web_search");
  });
  it("edits a deeper field without touching item siblings", () => {
    const r = setListItemScalar(
      LIST_FIXTURE,
      ["deployment"],
      ["mcp", "servers"],
      0,
      "label",
      "Search",
    );
    expect(r.applied).toBe(true);
    expect(r.text).toContain("label: Search");
    expect(r.text).toContain("url: https://search.internal/mcp");
    expect(r.text).toContain("token: __DEVKIT_PRESERVED__");
  });
  it("inserts a missing field after the dash line", () => {
    const r = setListItemScalar(
      LIST_FIXTURE,
      ["deployment"],
      ["tools", "catalog"],
      1,
      "default",
      true,
    );
    expect(r.applied).toBe(true);
    expect(r.text).toContain("- id: calculator\n        default: true");
  });
  it("refuses out-of-range indices and missing lists", () => {
    expect(setListItemScalar(LIST_FIXTURE, ["deployment"], ["tools", "catalog"], 9, "id", "x").applied).toBe(false);
    expect(setListItemScalar(LIST_FIXTURE, ["deployment"], ["tools", "nope"], 0, "id", "x").applied).toBe(false);
  });
});

describe("appendListItem / removeListItem", () => {
  it("appends to an existing list", () => {
    const r = appendListItem(LIST_FIXTURE, ["deployment"], ["tools", "catalog"], {
      id: "vault",
      label: "Vault",
    });
    expect(r.applied).toBe(true);
    expect(r.text).toContain("- id: vault\n        label: Vault");
  });
  it("creates a missing list chain", () => {
    const r = appendListItem(FIXTURE, ["deployment"], ["tools", "catalog"], { id: "vault" });
    expect(r.applied).toBe(true);
    expect(r.text).toContain("catalog:\n      - id: vault");
  });
  it("converts an inline empty list to a block list", () => {
    const empty = `version: 1
deployment:
  slug: demo-chat
  tools:
    catalog: []
`;
    const r = appendListItem(empty, ["deployment"], ["tools", "catalog"], { id: "vault" });
    expect(r.applied).toBe(true);
    expect(r.text).toContain("catalog:\n      - id: vault");
    expect(r.text).not.toContain("catalog: []");
  });
  it("refuses when the key owns a scalar", () => {
    const r = appendListItem(FIXTURE, ["deployment"], ["slug"], { id: "x" });
    expect(r.applied).toBe(false);
    expect(r.text).toBe(FIXTURE);
  });
  it("removes a middle item, keeping siblings", () => {
    const added = appendListItem(LIST_FIXTURE, ["deployment"], ["tools", "catalog"], { id: "vault" });
    const r = removeListItem(added.text, ["deployment"], ["tools", "catalog"], 1);
    expect(r.applied).toBe(true);
    expect(r.text).toContain("- id: web_search");
    expect(r.text).toContain("- id: vault");
    expect(r.text).not.toContain("calculator");
  });
  it("removing the last item renders an empty inline list", () => {
    const one = `version: 1
deployment:
  tools:
    catalog:
      - id: only
`;
    const r = removeListItem(one, ["deployment"], ["tools", "catalog"], 0);
    expect(r.applied).toBe(true);
    expect(r.text).toContain("catalog: []");
  });
});

describe("secretState", () => {
  it("classifies absent, sentinel, and value", () => {
    expect(secretState(LIST_FIXTURE, ["deployment"], ["token"])).toBe("absent");
    expect(secretState(LIST_FIXTURE, ["deployment"], ["mcp", "servers"])).toBe("value");
    const withToken = setScalar(LIST_FIXTURE, ["deployment"], ["token"], "s3cret");
    expect(secretState(withToken.text, ["deployment"], ["token"])).toBe("value");
    const sentinel = setScalar(LIST_FIXTURE, ["deployment"], ["token"], DEVKIT_SENTINEL);
    expect(secretState(sentinel.text, ["deployment"], ["token"])).toBe("sentinel");
  });
  it("classifies list-item secret fields", () => {
    expect(
      secretStateInList(LIST_FIXTURE, ["deployment"], ["mcp", "servers"], 0, "token"),
    ).toBe("sentinel");
    expect(
      secretStateInList(LIST_FIXTURE, ["deployment"], ["mcp", "servers"], 0, "label"),
    ).toBe("value");
    expect(
      secretStateInList(LIST_FIXTURE, ["deployment"], ["mcp", "servers"], 0, "missing"),
    ).toBe("absent");
    expect(
      secretStateInList(LIST_FIXTURE, ["deployment"], ["mcp", "servers"], 9, "token"),
    ).toBe("absent");
  });
});

describe("deleteListItemField", () => {
  it("splices a deeper field line", () => {
    const r = deleteListItemField(LIST_FIXTURE, ["deployment"], ["mcp", "servers"], 0, "label");
    expect(r.applied).toBe(true);
    expect(r.text).not.toContain("label: Digisearch");
    expect(r.text).toContain("- id: digisearch");
    expect(r.text).toContain("url: https://search.internal/mcp");
  });
  it("promotes the first content line when deleting a dash-inline field", () => {
    const r = deleteListItemField(LIST_FIXTURE, ["deployment"], ["mcp", "servers"], 0, "id");
    expect(r.applied).toBe(true);
    expect(r.text).toContain("- url: https://search.internal/mcp");
    expect(r.text).not.toContain("- id: digisearch");
  });
  it("refuses missing fields and bad indices", () => {
    expect(
      deleteListItemField(LIST_FIXTURE, ["deployment"], ["mcp", "servers"], 0, "nope").applied,
    ).toBe(false);
    expect(
      deleteListItemField(LIST_FIXTURE, ["deployment"], ["mcp", "servers"], 5, "id").applied,
    ).toBe(false);
  });
});

describe("applyAll", () => {
  it("chains edits and stops at the first refusal with text untouched", () => {
    const ok = applyAll(FIXTURE, [
      (t) => setScalar(t, ["deployment"], ["slug"], "renamed"),
      (t) => setScalar(t, ["deployment"], ["chrome", "theme"], "dark"),
    ]);
    expect(ok.applied).toBe(true);
    expect(ok.text).toContain("slug: renamed");
    expect(ok.text).toContain("theme: dark");
    const bad = applyAll(FIXTURE, [
      (t) => setScalar(t, ["deployment"], ["slug"], "renamed"),
      (t) => setScalar(t, ["nope"], ["x"], "y"),
    ]);
    expect(bad).toEqual({ text: FIXTURE, applied: false });
  });
});
