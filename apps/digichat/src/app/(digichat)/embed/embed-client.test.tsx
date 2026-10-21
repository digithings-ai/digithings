// @vitest-environment happy-dom
/**
 * Trial proof presenter (DIG-4523).
 *
 * The embedding page hands over a server-signed, host-scoped trial proof over
 * postMessage. The client holds it in memory only and reads it at send time.
 *
 * Two things are pinned here:
 *   1. the message gate — a proof is only taken from the origin we serve, and
 *      never for another host;
 *   2. the in-memory-only rule — the proof never reaches storage and never
 *      reaches a URL.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { UIMessage } from "ai";
import { useEmbedDigiChat } from "@/hooks/use-embed-digi-chat";
import {
  embedParentOrigin,
  readTrialProofMessage,
  TRIAL_PROOF_MESSAGE_TYPE,
  useTrialProofChannel,
} from "./embed-client";

const embedClientSrc = readFileSync(join(__dirname, "embed-client.tsx"), "utf8");

/** Code lines only — comments state the rule, they do not implement it. */
function codeLinesOf(source: string): string[] {
  return source
    .split("\n")
    .filter((line) => {
      const trimmed = line.trim();
      return (
        trimmed.length > 0 &&
        !trimmed.startsWith("//") &&
        !trimmed.startsWith("*") &&
        !trimmed.startsWith("/*")
      );
    });
}

const proofCodeLines = codeLinesOf(embedClientSrc).filter((line) =>
  /trialProof|getTrialProof|TRIAL_PROOF|trial:proof/.test(line),
);

/**
 * A line without its trailing comment.
 *
 * A pin that reads a comment reads nothing: prose can carry the marker, so
 * the pin would read the prose while the wiring says something else, and a
 * word in prose can stand in for the wiring, so the pin would pass on code
 * that no longer names the backend. The scan runs on code only.
 */
function stripTrailingComment(line: string): string {
  let quote: string | null = null;
  for (let i = 0; i < line.length; i++) {
    const ch = line.charAt(i);
    if (quote !== null) {
      if (ch === quote) quote = null;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === "`") {
      quote = ch;
      continue;
    }
    if (ch === "/" && line.charAt(i + 1) === "/") return line.slice(0, i);
  }
  return line;
}

/**
 * The statement that wires the provider label.
 *
 * The wiring is one property, so the statement is the property line plus
 * the lines its brackets span. The marker has to start a line: a marker
 * inside a comment, or inside another statement, is not the wiring. The
 * marker has to appear exactly once, so a second site fails loudly instead
 * of quietly re-targeting the pin.
 */
function providerLabelStatement(source: string): string {
  const lines = codeLinesOf(source).map(stripTrailingComment);
  const sites = lines.filter((line) => /^\s*providerLabel\s*:/.test(line));
  if (sites.length !== 1) {
    throw new Error(
      `the source wires ${sites.length} provider labels, expected exactly one`,
    );
  }
  const at = lines.indexOf(sites[0]);
  const markerAt = sites[0].indexOf("providerLabel");
  const colonAt = sites[0].indexOf(":", markerAt);
  let statement = sites[0].slice(colonAt + 1);
  const open = (line: string) => (line.match(/\(/g) ?? []).length;
  const close = (line: string) => (line.match(/\)/g) ?? []).length;
  let depth = open(statement) - close(statement);
  let next = at + 1;
  while (depth > 0 && next < lines.length) {
    const line = lines[next];
    statement += `\n${line}`;
    depth += open(line) - close(line);
    next += 1;
  }
  // The trailing comma belongs to the object literal around the wiring.
  return statement.trim().replace(/,$/, "").trim();
}

// ---------------------------------------------------------------------------
// DIG-4538: the expired-proof signal.
//
// The proof lifecycle is proved behaviourally here, not by reading the
// source: a proof is handed to a rendered client, the server answers with
// the expired signal, and the client must drop the proof, ask the page for
// a fresh one exactly once, and present nothing on the next request.
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

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const PARENT_ORIGIN = "https://tenant.example";
const PROOF = "hmac.trial.proof";

/**
 * The proof the client holds is read back through the request it builds:
 * that is the only way it is ever used, so the request header is the
 * observable form of "the client holds a proof".
 */
function TrialProofBed() {
  const { getTrialProof, onTrialProofExpired } = useTrialProofChannel(PARENT_ORIGIN);
  useEmbedDigiChat({
    accent: "#4f46e5",
    embedHost: PARENT_ORIGIN,
    getTrialProof,
    onTrialProofExpired,
  });
  return null;
}

function renderTrialProofBed(): { unmount: () => void } {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(createElement(TrialProofBed));
  });
  return {
    unmount: () => {
      act(() => {
        root.unmount();
      });
      container.remove();
    },
  };
}

function deliverProof(proof: string, origin: string = PARENT_ORIGIN): void {
  const event = new MessageEvent("message", {
    data: { type: "trial:proof", proof },
  });
  Object.defineProperty(event, "origin", { value: origin, configurable: true });
  act(() => {
    window.dispatchEvent(event);
  });
}

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

/** Build the request the transport would send and hand it to its fetch. */
async function sendChatRequest(): Promise<Headers> {
  const config = readCapturedTransportConfig();
  if (!config?.fetch) {
    throw new Error("the transport carries no fetch");
  }
  const prepared = await config.prepareSendMessagesRequest({
    messages: [],
    body: undefined,
  });
  const headers = new Headers(prepared.headers);
  await config.fetch(`${PARENT_ORIGIN}/api/chat`, { method: "POST", headers });
  return headers;
}

/** Answer the chat request with the given response headers. */
async function answerWith(headers: Record<string, string>): Promise<Headers> {
  warmFetchMock.mockResolvedValue(new Response(null, { status: 200, headers }));
  return sendChatRequest();
}

type StorageWrite = { area: string; op: string; key: string; value: string };

/**
 * Replace both storage areas with a recording stub for the duration of a
 * check. The environment has no localStorage at all - the runtime exposes
 * it only behind a file flag - so a stub is the only way to observe a
 * write. Reads still reach the real store, so nothing else changes.
 */
function watchStorageWrites(): { writes: StorageWrite[]; restore: () => void } {
  const writes: StorageWrite[] = [];
  const restores: Array<() => void> = [];
  const install = (target: unknown, area: string) => {
    if (!target || typeof target !== "object") return;
    const holder = target as Record<string, unknown>;
    const descriptor = Object.getOwnPropertyDescriptor(holder, area);
    const original = holder[area] as Storage | undefined;
    const stub = {
      get length() {
        return original?.length ?? 0;
      },
      getItem: (key: string) => original?.getItem?.(key) ?? null,
      key: (index: number) => original?.key?.(index) ?? null,
      removeItem: (key: string) => {
        writes.push({ area, op: "removeItem", key, value: "" });
        original?.removeItem?.(key);
      },
      clear: () => {
        writes.push({ area, op: "clear", key: "", value: "" });
        original?.clear?.();
      },
      setItem: (key: string, value: string) => {
        writes.push({ area, op: "setItem", key, value: String(value) });
        original?.setItem?.(key, value);
      },
    };
    try {
      Object.defineProperty(holder, area, {
        value: stub,
        configurable: true,
        writable: true,
      });
      restores.push(() => {
        if (descriptor) {
          Object.defineProperty(holder, area, descriptor);
        } else {
          delete holder[area];
        }
      });
    } catch {
      // The area cannot be observed here.
    }
  };
  install(globalThis, "localStorage");
  install(globalThis, "sessionStorage");
  install((globalThis as { window?: unknown }).window, "localStorage");
  install((globalThis as { window?: unknown }).window, "sessionStorage");
  return {
    writes,
    restore: () => {
      restores.forEach((undo) => undo());
    },
  };
}

describe("embed parent origin", () => {
  it("derives the origin of the page that embeds us", () => {
    expect(embedParentOrigin("https://tenant.example")).toBe("https://tenant.example");
    expect(embedParentOrigin("tenant.example")).toBe("https://tenant.example");
  });

  it("drops the path when the host is given as a full URL", () => {
    expect(embedParentOrigin("https://tenant.example/chat?a=1")).toBe(
      "https://tenant.example",
    );
  });

  it("has no origin when no host is served", () => {
    expect(embedParentOrigin(undefined)).toBeNull();
    expect(embedParentOrigin("   ")).toBeNull();
  });
});

describe("readTrialProofMessage", () => {
  const options = {
    parentOrigin: "https://tenant.example",
    servingHost: "https://tenant.example",
  };

  it("takes the proof from the origin we serve", () => {
    const proof = readTrialProofMessage(
      {
        origin: "https://tenant.example",
        data: { type: TRIAL_PROOF_MESSAGE_TYPE, proof: "hmac.trial.proof" },
      },
      options,
    );
    expect(proof).toBe("hmac.trial.proof");
  });

  it("ignores a proof posted from another origin", () => {
    const proof = readTrialProofMessage(
      {
        origin: "https://evil.example",
        data: { type: TRIAL_PROOF_MESSAGE_TYPE, proof: "hmac.trial.proof" },
      },
      options,
    );
    expect(proof).toBeNull();
  });

  it("ignores a message of another type", () => {
    const proof = readTrialProofMessage(
      {
        origin: "https://tenant.example",
        data: { type: "digichat:plan-tier", proof: "hmac.trial.proof" },
      },
      options,
    );
    expect(proof).toBeNull();
  });

  it("ignores an empty proof", () => {
    const proof = readTrialProofMessage(
      {
        origin: "https://tenant.example",
        data: { type: TRIAL_PROOF_MESSAGE_TYPE, proof: "   " },
      },
      options,
    );
    expect(proof).toBeNull();
  });

  it("rejects a proof sent under another field name", () => {
    const proof = readTrialProofMessage(
      {
        origin: "https://tenant.example",
        data: { type: TRIAL_PROOF_MESSAGE_TYPE, token: "hmac.trial.proof" },
      },
      options,
    );
    expect(proof).toBeNull();
  });

  it("ignores a proof that names another host", () => {
    const proof = readTrialProofMessage(
      {
        origin: "https://tenant.example",
        data: {
          type: TRIAL_PROOF_MESSAGE_TYPE,
          proof: "hmac.trial.proof",
          host: "https://other.example",
        },
      },
      options,
    );
    expect(proof).toBeNull();
  });

  it("accepts a proof that names the host we serve in another spelling", () => {
    const proof = readTrialProofMessage(
      {
        origin: "https://tenant.example",
        data: {
          type: TRIAL_PROOF_MESSAGE_TYPE,
          proof: "hmac.trial.proof",
          host: "tenant.example",
        },
      },
      options,
    );
    expect(proof).toBe("hmac.trial.proof");
  });
});

describe("trial proof is held in memory only", () => {
  it("pins the code that carries the proof", () => {
    expect(proofCodeLines.length).toBeGreaterThan(0);
  });

  it("never writes the proof to storage", () => {
    for (const line of proofCodeLines) {
      expect(line).not.toMatch(/localStorage|sessionStorage|setItem|getItem|indexedDB/);
    }
  });

  it("never puts the proof in a URL", () => {
    for (const line of proofCodeLines) {
      expect(line).not.toMatch(/new URL\(|searchParams|href|location\.|URLSearchParams/);
    }
  });

  it("keeps the proof in a ref and reads it through a getter", () => {
    expect(embedClientSrc).toMatch(/useRef<string \| null>\(null\)/);
    expect(embedClientSrc).toMatch(/const getTrialProof = useCallback\(\(\) => trialProofRef\.current/);
    expect(embedClientSrc).toMatch(/getTrialProof,/);
  });

  it("never clears the proof on the unlock path", () => {
    // The page posts the proof before the unlock, so the proof is still
    // needed when the unlock arrives: no line that touches the proof may
    // be driven by the unlock.
    for (const line of proofCodeLines) {
      expect(line).not.toMatch(/unlock/i);
    }
  });

  it("uses a message type that names no client", () => {
    expect(TRIAL_PROOF_MESSAGE_TYPE).toBe("trial:proof");
  });
});

describe("an expired trial proof is dropped and the page is asked for a new one", () => {
  beforeEach(() => {
    capturedTransportConfig = undefined;
    warmFetchMock.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("holds the proof the page sends and presents it on the next request", async () => {
    const postSpy = vi.spyOn(window.parent, "postMessage").mockImplementation(() => {});
    const { unmount } = renderTrialProofBed();

    deliverProof(PROOF);

    const headers = await preparedHeaders();
    expect(headers.get("X-Embed-Trial-Proof")).toBe(PROOF);
    expect(postSpy).not.toHaveBeenCalled();

    unmount();
  });

  it("drops the proof on the expired signal and asks the page exactly once", async () => {
    const postSpy = vi.spyOn(window.parent, "postMessage").mockImplementation(() => {});
    const { unmount } = renderTrialProofBed();
    deliverProof(PROOF);

    await answerWith({ "x-embed-trial-proof-expired": "1" });

    expect(postSpy).toHaveBeenCalledTimes(1);
    expect(postSpy).toHaveBeenCalledWith(
      { type: "trial:proof-refresh" },
      PARENT_ORIGIN,
    );

    const next = await preparedHeaders();
    expect(next.get("X-Embed-Trial-Proof")).toBeNull();

    unmount();
  });

  it("does not ask again when the same signal repeats", async () => {
    const postSpy = vi.spyOn(window.parent, "postMessage").mockImplementation(() => {});
    const { unmount } = renderTrialProofBed();
    deliverProof(PROOF);

    await answerWith({ "x-embed-trial-proof-expired": "1" });
    await answerWith({ "x-embed-trial-proof-expired": "1" });

    expect(postSpy).toHaveBeenCalledTimes(1);

    unmount();
  });

  it("does not ask on any other response", async () => {
    const postSpy = vi.spyOn(window.parent, "postMessage").mockImplementation(() => {});
    const { unmount } = renderTrialProofBed();
    deliverProof(PROOF);

    await answerWith({});
    await answerWith({ "x-embed-trial-proof-expired": "0" });
    await answerWith({ "x-embed-trial-proof-expired": "" });

    expect(postSpy).not.toHaveBeenCalled();
    const headers = await preparedHeaders();
    expect(headers.get("X-Embed-Trial-Proof")).toBe(PROOF);

    unmount();
  });

  it("keeps the proof out of storage and out of every request", async () => {
    vi.spyOn(window.parent, "postMessage").mockImplementation(() => {});
    const storage = watchStorageWrites();
    try {
      // The instrument must be able to see a write at all.
      globalThis.sessionStorage.setItem("__probe__", "x");
      expect(storage.writes.length).toBeGreaterThan(0);
      storage.writes.length = 0;

      const { unmount } = renderTrialProofBed();
      deliverProof(PROOF);

      const first = await answerWith({});
      expect(first.get("X-Embed-Trial-Proof")).toBe(PROOF);

      await answerWith({ "x-embed-trial-proof-expired": "1" });

      expect(
        storage.writes.filter(
          (write) => write.key.includes(PROOF) || write.value.includes(PROOF),
        ),
      ).toEqual([]);
      expect(warmFetchMock.mock.calls.length).toBeGreaterThan(0);
      for (const call of warmFetchMock.mock.calls) {
        // The proof travels in a header, never in the URL and never in the body.
        expect(String(call[0])).not.toContain(PROOF);
        const init = (call[1] ?? {}) as RequestInit;
        expect(typeof init.body === "string" ? init.body : "").not.toContain(PROOF);
        const headers = new Headers(init.headers as HeadersInit);
        for (const [name, value] of headers.entries()) {
          if (name.toLowerCase() === "x-embed-trial-proof") continue;
          expect(value).not.toContain(PROOF);
        }
      }

      unmount();
    } finally {
      storage.restore();
    }
  });
});

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
    const wiring = providerLabelStatement(embedClientSrc);
    // The shared helper owns the naming: the app has one vocabulary.
    expect(wiring).toMatch(/^backendLabel\(/);
    // The own-key provider wins while the session carries a key, and it is
    // the first thing the helper is given: the state is not inverted and
    // the arguments are not swapped.
    expect(wiring).toMatch(
      /^backendLabel\(\s*byokIsSet\s*\?\s*byokProvider\s*:\s*null\s*,/,
    );
    expect(wiring).not.toMatch(/!\s*byokIsSet/);
    // The backend that serves the chat is named too, so a Foundry tenant
    // does not get the house backend's name. The source of that backend is
    // named, not any local that happens to be called backendType.
    expect(wiring).toMatch(/,\s*stockClient\.backendType\s*,?\s*\)$/);
    // No literal backend name: a copy of one drifts the moment the house
    // backend changes.
    expect(wiring).not.toMatch(/["'`]/);
  });

  it("reads the naming helper from its one home, not from a local copy", () => {
    const helperImport =
      /import\s*\{[^}]*\bbackendLabel\b[^}]*\}\s*from\s*["']@\/lib\/provider-label["']/g;
    expect(embedClientSrc.match(helperImport)).toHaveLength(1);
    // A local copy of the helper shadows the import and answers with a
    // label of its own.
    expect(embedClientSrc).not.toMatch(
      /(?:const|let|var|function)\s+backendLabel\b/,
    );
  });
});
