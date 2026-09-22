import { describe, expect, it } from "vitest";
import {
  DIGIGRAPH_PORT,
  DIGIKEY_PORT,
  DIGISEARCH_PORT,
  portForHostname,
} from "./ports";

describe("portForHostname", () => {
  it("routes graph.digithings.ai to digigraph", () => {
    expect(portForHostname("graph.digithings.ai")).toBe(DIGIGRAPH_PORT);
  });

  it("routes key.digithings.ai to digikey", () => {
    expect(portForHostname("key.digithings.ai")).toBe(DIGIKEY_PORT);
  });

  it("routes search.digithings.ai to digisearch", () => {
    expect(portForHostname("search.digithings.ai")).toBe(DIGISEARCH_PORT);
  });

  it("routes any search.* host to digisearch (same prefix rule as graph.*/key.*)", () => {
    expect(portForHostname("search.example.com")).toBe(DIGISEARCH_PORT);
  });

  it("defaults workers.dev / localhost to digigraph", () => {
    expect(portForHostname("digithings-stack.example.workers.dev")).toBe(
      DIGIGRAPH_PORT,
    );
    expect(portForHostname("localhost")).toBe(DIGIGRAPH_PORT);
  });

  it("rejects unknown hosts", () => {
    expect(portForHostname("evil.example.com")).toBeNull();
  });
});
