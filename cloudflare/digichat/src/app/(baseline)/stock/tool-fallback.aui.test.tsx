// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ToolFallback, formatToolDuration } from "./tool-fallback.aui";

describe("stock ToolFallback", () => {
  it("renders the digisearch row with the raw backend id", () => {
    render(
      <ToolFallback
        type="tool-call"
        toolCallId="t1"
        toolName="digisearch"
        args={{ query: "jwt", mode: "keyword" }}
        argsText='{"query":"jwt","mode":"keyword"}'
        status={{ type: "complete" }}
        addResult={() => undefined}
        resume={() => undefined}
        respondToApproval={async () => undefined}
      />,
    );
    expect(screen.getByText("digisearch")).toBeTruthy();
    expect(screen.queryByText("digisearch keyword")).toBeNull();
  });

  it("renders vault tool ids verbatim in the row title", () => {
    render(
      <ToolFallback
        type="tool-call"
        toolCallId="t2"
        toolName="digivault_get_note"
        args={{ vault_paths: ["a.md"] }}
        argsText='{"vault_paths":["a.md"]}'
        status={{ type: "complete" }}
        addResult={() => undefined}
        resume={() => undefined}
        respondToApproval={async () => undefined}
      />,
    );
    expect(screen.getByText("digivault_get_note")).toBeTruthy();
    expect(screen.queryByText("digivault get note")).toBeNull();
  });
});

describe("stock formatToolDuration", () => {
  it("shows bare milliseconds under one second", () => {
    expect(formatToolDuration(0)).toBe("0ms");
    expect(formatToolDuration(412)).toBe("412ms");
    expect(formatToolDuration(999)).toBe("999ms");
  });

  it("shows dual-unit seconds and milliseconds at 1s and above", () => {
    expect(formatToolDuration(1000)).toBe("1.0s (1000ms)");
    expect(formatToolDuration(2300)).toBe("2.3s (2300ms)");
    expect(formatToolDuration(65000)).toBe("1m 5s (65000ms)");
  });
});
