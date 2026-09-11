import { describe, expect, it } from "vitest";
import {
  assertCliEnabled,
  buildDigichatChatHeaders,
  digichatChatUrl,
  normalizeDigichatBaseUrl,
} from "./chat-request.js";
import { createDigichatTransport } from "./transport.js";

describe("normalizeDigichatBaseUrl", () => {
  it("strips trailing slash and path", () => {
    expect(normalizeDigichatBaseUrl("http://127.0.0.1:3005/")).toBe(
      "http://127.0.0.1:3005",
    );
  });

  it("fails closed on empty", () => {
    expect(() => normalizeDigichatBaseUrl("  ")).toThrow(/required/);
  });
});

describe("digichatChatUrl", () => {
  it("appends /api/chat", () => {
    expect(digichatChatUrl("http://localhost:3005")).toBe(
      "http://localhost:3005/api/chat",
    );
  });
});

describe("buildDigichatChatHeaders", () => {
  it("sets embed token + optional host/model/language", () => {
    const h = buildDigichatChatHeaders({
      baseUrl: "http://localhost:3005",
      auth: { kind: "embed", token: "tok_abc", host: "digithings.ai" },
      language: "de",
      model: "gpt-4o-mini",
      sessionId: "sess-1",
    });
    expect(h["x-embed-token"]).toBe("tok_abc");
    expect(h["x-embed-host"]).toBe("digithings.ai");
    expect(h["x-digi-language"]).toBe("de");
    expect(h["x-digi-model"]).toBe("gpt-4o-mini");
    expect(h["x-digichat-session"]).toBe("sess-1");
    expect(h["x-digi-caller"]).toBe("digichat-cli");
  });

  it("sets bearer for api_key auth", () => {
    const h = buildDigichatChatHeaders({
      baseUrl: "http://localhost:3005",
      auth: { kind: "api_key", apiKey: "dgk_live_x" },
    });
    expect(h.authorization).toBe("Bearer dgk_live_x");
    expect(h["x-embed-token"]).toBeUndefined();
  });
});

describe("createDigichatTransport", () => {
  it("builds an AssistantChatTransport against /api/chat", () => {
    const transport = createDigichatTransport({
      baseUrl: "http://127.0.0.1:3005",
      auth: { kind: "none" },
    });
    expect(transport).toBeDefined();
    expect(typeof transport.sendMessages).toBe("function");
  });
});

describe("assertCliEnabled", () => {
  it("allows enabled: true", () => {
    expect(() => assertCliEnabled({ cli: { enabled: true } })).not.toThrow();
  });

  it("fails closed when missing or false", () => {
    expect(() => assertCliEnabled({})).toThrow(/cli\.enabled/);
    expect(() => assertCliEnabled({ cli: { enabled: false } })).toThrow(
      /cli\.enabled/,
    );
    expect(() => assertCliEnabled(null)).toThrow(/cli\.enabled/);
  });
});
