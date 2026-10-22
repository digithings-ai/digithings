import { describe, expect, it } from "vitest";

import { connectionStatusText } from "./connection-status";

const conn = (data: unknown) => ({ type: "data", name: "connection", data });

describe("connectionStatusText", () => {
  it("is null when no status part arrived", () => {
    expect(connectionStatusText([])).toBeNull();
  });

  it("is null for a bare state without a message", () => {
    expect(connectionStatusText([conn({ state: "connecting" })])).toBeNull();
    expect(connectionStatusText([conn({ state: "warming_up" })])).toBeNull();
    expect(connectionStatusText([conn({ state: "warming_up", message: "  " })])).toBeNull();
  });

  it("returns the exact message the server sent", () => {
    expect(
      connectionStatusText([
        conn({ state: "connecting" }),
        conn({ state: "warming_up", message: "Waking up services…" }),
      ]),
    ).toBe("Waking up services…");
    expect(
      connectionStatusText([
        conn({ state: "warming_up", message: "Waiting for model capacity — retrying in 8s" }),
      ]),
    ).toBe("Waiting for model capacity — retrying in 8s");
  });

  it("clears once the connection settles", () => {
    expect(
      connectionStatusText([
        conn({ state: "warming_up", message: "Waking up services…" }),
        conn({ state: "connected" }),
      ]),
    ).toBeNull();
    expect(
      connectionStatusText([
        conn({ state: "warming_up", message: "Waiting for model capacity" }),
        conn({ state: "ready" }),
      ]),
    ).toBeNull();
  });

  it("ignores other data parts", () => {
    expect(
      connectionStatusText([{ type: "data", name: "status", data: { message: "x" } }]),
    ).toBeNull();
  });
});
