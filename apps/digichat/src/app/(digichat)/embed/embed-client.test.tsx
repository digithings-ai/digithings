// @vitest-environment happy-dom
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { UIMessage } from "ai";
import type { EmbedTenantClientConfig } from "@/lib/embed-client-config";
import EmbedClient from "./embed-client";

const embedClientSrc = readFileSync(join(__dirname, "embed-client.tsx"), "utf8");

/**
 * The source with its comments removed.
 *
 * A pin that reads a comment reads nothing: a comment can carry the marker
 * (the pin would read the prose while the wiring says something else) and a
 * word in prose can stand in for the wiring (the pin would pass on code that
 * no longer names the backend). The comments become spaces, so the code keeps
 * its place and the line of a site does not move.
 */
function codeOnly(source: string): string {
  let out = "";
  let i = 0;
  let quote: string | null = null;
  while (i < source.length) {
    const ch = source.charAt(i);
    const next = source.charAt(i + 1);
    if (quote !== null) {
      out += ch;
      if (ch === "\\" && i + 1 < source.length) {
        out += next;
        i += 2;
        continue;
      }
      if (ch === quote) quote = null;
      i += 1;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === "`") {
      quote = ch;
      out += ch;
      i += 1;
      continue;
    }
    if (ch === "/" && next === "/") {
      while (i < source.length && source.charAt(i) !== "\n") {
        out += " ";
        i += 1;
      }
      continue;
    }
    if (ch === "/" && next === "*") {
      while (
        i < source.length &&
        !(source.charAt(i) === "*" && source.charAt(i + 1) === "/")
      ) {
        out += source.charAt(i) === "\n" ? "\n" : " ";
        i += 1;
      }
      out += "  ";
      i += 2;
      continue;
    }
    out += ch;
    i += 1;
  }
  return out;
}

/**
 * The expression that wires the provider label.
 *
 * The wiring is one property, so the expression is the whole statement: it
 * ends at the first comma or semicolon outside brackets and parentheses, so
 * a call that spans several lines is captured whole. The marker has to
 * appear exactly once: a second site fails loudly instead of quietly
 * re-targeting the pin.
 */
function providerLabelExpression(code: string): string {
  // The label is named once in the file. A second mention - a second
  // property, an assignment, a computed key - is a second naming of it,
  // wherever it is written.
  const mentions = (code.match(/providerLabel/g) ?? []).length;
  const sites = [...code.matchAll(/providerLabel\s*:/g)];
  if (mentions !== 1 || sites.length !== 1) {
    throw new Error(
      `the source names the provider label ${mentions} time(s), expected once`,
    );
  }
  const at = (sites[0].index ?? 0) + sites[0][0].length;
  const rest = code.slice(at);
  let depth = 0;
  let quote: string | null = null;
  for (let i = 0; i < rest.length; i++) {
    const ch = rest.charAt(i);
    if (quote !== null) {
      if (ch === quote) quote = null;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === "`") {
      quote = ch;
      continue;
    }
    if (ch === "(" || ch === "[" || ch === "{") {
      depth++;
      continue;
    }
    if (ch === ")" || ch === "]" || ch === "}") {
      depth--;
      if (depth < 0) break;
      continue;
    }
    if (depth === 0 && (ch === "," || ch === ";")) {
      return rest.slice(0, i).trim();
    }
  }
  return rest.trim();
}

/** The expression without the whitespace and the casts formatting may change. */
function normalised(expression: string): string {
  return expression
    .replace(/\s+/g, " ")
    .replace(/\(\s+/g, "(")
    .replace(/\s+\)/g, ")")
    .replace(/,\)/g, ")")
    .replace(/\s+as\s+[A-Za-z_$][\w$]*/g, "")
    .trim();
}

// ---------------------------------------------------------------------------
// The shared transport harness.
//
// The transport is captured rather than reimplemented: the assertions run
// against the real closure the hook builds.
//
// @testing-library/react's renderHook is not used: it is hoisted to the
// repo-root node_modules and resolves a different react copy than the
// files under test, which trips React's "Invalid hook call". The hand-rolled
// harness below renders with the same local react the hook uses.
// ---------------------------------------------------------------------------

type PrepareSendMessagesRequestResult = {
  headers: Record<string, string>;
  body: unknown;
};
type PrepareSendMessagesRequestFn = (args: {
  messages: UIMessage[];
  body?: unknown;
  trigger?: "submit-message" | "regenerate-message";
}) => PrepareSendMessagesRequestResult | Promise<PrepareSendMessagesRequestResult>;

type CapturedTransportConfig = {
  prepareSendMessagesRequest: PrepareSendMessagesRequestFn;
  fetch?: typeof fetch;
};

let capturedTransportConfig: CapturedTransportConfig | undefined;

function readCapturedTransportConfig(): CapturedTransportConfig | undefined {
  return capturedTransportConfig;
}

const warmFetchMock = vi.hoisted(() => vi.fn());

vi.mock("@ai-sdk/react", () => ({
  useChat: vi.fn(() => ({
    id: "test-chat",
    messages: [],
    sendMessage: vi.fn(),
    status: "ready",
    error: undefined,
    regenerate: vi.fn(),
    setMessages: vi.fn(),
    stop: vi.fn(),
  })),
}));

vi.mock("@assistant-ui/ai-sdk", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@assistant-ui/ai-sdk")>();
  return {
    ...actual,
    AssistantChatTransport: vi.fn().mockImplementation(function (config: unknown) {
      capturedTransportConfig = config as CapturedTransportConfig;
      return new actual.AssistantChatTransport(
        config as ConstructorParameters<typeof actual.AssistantChatTransport>[0],
      );
    }),
    useAISDKRuntime: () => ({ kind: "runtime" }),
  };
});

vi.mock("@/lib/warmup-gate", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/warmup-gate")>();
  return { ...actual, warmFetch: warmFetchMock };
});

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));

// The model header is set in EmbedChat, before this shell paints. The shell
// needs a live assistant runtime, which this file does not build.
vi.mock("@/components/stock/product-shell", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/components/stock/product-shell")>();
  return { ...actual, ProductStockShell: () => null };
});

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

async function preparedHeaders(): Promise<Headers> {
  const config = readCapturedTransportConfig();
  if (!config) {
    throw new Error("the transport was never constructed");
  }
  const result = await config.prepareSendMessagesRequest({
    messages: [],
    body: undefined,
  });
  return new Headers(result.headers);
}

// ---------------------------------------------------------------------------
// DIG-4879: the composer provider chip on the embed surface.
//
// The chip names the backend that serves the chat (ARCHITECTURE.md, "The
// composer provider chip names the backend that serves the chat"). The embed
// surface is the only one that can name its own backend, so its label has to
// follow the session: the own-key provider while a key is set, the backend
// type otherwise.
//
// The wiring is pinned from the source, the house pattern of this file. It
// has to be: the rendered chip reads the same label whether the wiring
// derives it or hard-codes today's value, so a render cannot see the
// difference - only the source can.
// ---------------------------------------------------------------------------

describe("the embed composer provider chip", () => {
  it("derives the label from the BYOK state and the serving backend, not from a literal", () => {
    const wiring = normalised(providerLabelExpression(codeOnly(embedClientSrc)));
    // The whole wiring, pinned: the shared helper owns the naming, the
    // own-key provider comes first and is not inverted, the backend that
    // serves the chat comes second, and no literal names a backend.
    expect(wiring).toBe(
      "backendLabel(byokIsSet ? byokProvider : null, stockClient.backendType)",
    );
  });

  it("reads the naming helper from its one home, not from a local copy", () => {
    const code = codeOnly(embedClientSrc);
    const helperImport =
      /import\s*\{[^}]*\bbackendLabel\b[^}]*\}\s*from\s*["'](?:@\/lib\/|\.{1,2}\/)*provider-label["']/g;
    // The helper is named twice: in the import and in the wiring. A local
    // copy, a shadowed parameter or a destructured binding would name it a
    // third time.
    expect((code.match(/\bbackendLabel\b/g) ?? []).length).toBe(2);
    expect(code.match(helperImport)).toHaveLength(1);
  });
});

/**
 * Live house tenant: empty model list, plus a curated default. Seeding that
 * default would send X-Digi-Model. Develop's empty-list seed does not.
 */
const HOUSE_TENANT: EmbedTenantClientConfig = {
  slug: "digithings",
  gateMode: "ungated",
  theme: "dark",
  skin: "digichat",
  accent: null,
  attribution: true,
  backendType: "digigraph",
  models: { available: [], default: "deepseek/deepseek-v4.1-flash-1017" },
};

describe("a default house turn sends no X-Digi-Model", () => {
  beforeEach(() => {
    capturedTransportConfig = undefined;
    document.cookie = "digichat_byok_pref=; path=/; max-age=0";
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("omits the header when the embed client seeds an empty house list", async () => {
    const code = codeOnly(embedClientSrc);
    expect(code).toMatch(/model:\s*sessionModelSeed\(/);
    expect(code).toMatch(/modelSentOnTurn\(\s*chatPrefsRef\.current\.model/);
    expect(code).toMatch(/showContextMeter:\s*contextMeterEnabled\(/);
    expect(code).toMatch(
      /meterModel:\s*contextMeterModel\(\{\s*sessionModel:\s*modelSentOnTurn\(\s*chatPrefs\.model/,
    );

    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => {
      root.render(createElement(EmbedClient, { initialTenantCfg: HOUSE_TENANT }));
    });
    try {
      const headers = await preparedHeaders();
      expect(headers.get("X-Digi-Model")).toBeNull();
      expect(headers.get("X-BYOK-Model")).toBeNull();
    } finally {
      await act(async () => {
        root.unmount();
      });
      container.remove();
    }
  });
});
