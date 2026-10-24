import { describe, expect, it } from "vitest";
import { expandExtendsDocument } from "./extends-merge";

const house = {
  version: 1,
  embedHosts: ["digithings.ai", "www.digithings.ai"],
  deployment: {
    slug: "digithings-ai",
    backend: { type: "digigraph", digisearchIndex: "digithings_docs" },
    gate: { showContextMeter: true, webSearch: true },
    guardrails: { tokensPerMinute: { user: 80000 } },
    models: { catalog: true, default: "deepseek/deepseek-v4.1-flash-1017" },
    prompt: "house prompt",
  },
  hosts: {
    "digithings.ai": { slug: "digithings-ai" },
  },
};

describe("extends merge", () => {
  it("unions embed hosts, deletes with null, and replaces a different backend", () => {
    const read = (name: string) => {
      if (name !== "defaults") throw new Error(name);
      return house;
    };
    const expanded = expandExtendsDocument(
      {
        version: 1,
        extends: "defaults",
        embedHosts: ["localhost"],
        deployment: {
          slug: "trial",
          backend: { type: "foundry", agentName: "REPLACE-AGENT-NAME" },
          gate: { showContextMeter: null, webSearch: false },
          guardrails: null,
          prompt: null,
          models: { catalog: false, default: null },
        },
        hosts: null,
      },
      read,
    ) as {
      embedHosts: string[];
      deployment: Record<string, unknown>;
      hosts?: unknown;
    };
    expect(expanded.embedHosts).toEqual(["digithings.ai", "www.digithings.ai", "localhost"]);
    expect(expanded.hosts).toBeUndefined();
    expect(expanded.deployment.backend).toEqual({
      type: "foundry",
      agentName: "REPLACE-AGENT-NAME",
    });
    expect(expanded.deployment.guardrails).toBeUndefined();
    expect(expanded.deployment.prompt).toBeUndefined();
    expect(expanded.deployment.gate).toEqual({ webSearch: false });
    expect(expanded.deployment.models).toEqual({ catalog: false });
  });

  it("clones house onto a new host and drops the house host map", () => {
    const expanded = expandExtendsDocument(
      {
        version: 1,
        extends: "defaults",
        deployment: null,
        hosts: {
          "occ.digithings.ai": {
            slug: "occ",
            backend: { digisearchIndex: null },
            gate: { showContextMeter: null, webSearch: false },
            guardrails: null,
          },
        },
      },
      () => house,
    ) as { deployment?: unknown; hosts: Record<string, Record<string, unknown>> };
    expect(expanded.deployment).toBeUndefined();
    expect(Object.keys(expanded.hosts)).toEqual(["occ.digithings.ai"]);
    expect(expanded.hosts["occ.digithings.ai"]?.slug).toBe("occ");
    expect(expanded.hosts["occ.digithings.ai"]?.backend).toEqual({ type: "digigraph" });
    expect(expanded.hosts["occ.digithings.ai"]?.guardrails).toBeUndefined();
    expect(
      (expanded.hosts["occ.digithings.ai"]?.gate as { showContextMeter?: boolean })
        .showContextMeter,
    ).toBeUndefined();
  });
});
