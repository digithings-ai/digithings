import { describe, expect, it } from "vitest";

import { toMermaid, type ArchSpec } from "./ArchitectureDiagram";

const SPEC: ArchSpec = {
  title: "Example stack",
  description: "Two services in a boundary, one calling the other.",
  groups: [{ id: "zone", label: "your hosts", icon: "server" }],
  services: [
    { id: "app", label: "your app", icon: "internet" },
    { id: "graph", label: "orchestrator", icon: "server", group: "zone" },
    { id: "db", label: "store", icon: "database", group: "zone" },
  ],
  edges: [
    { from: "app", to: "graph", fromSide: "B", toSide: "T" },
    { from: "graph", to: "db", fromSide: "R", toSide: "L", arrow: "none" },
  ],
};

describe("toMermaid", () => {
  it("opens with the architecture-beta header and carries the accessible title", () => {
    const source = toMermaid(SPEC);
    expect(source.split("\n")[0]).toBe("architecture-beta");
    expect(source).toContain("accTitle: Example stack");
    expect(source).toContain("accDescr: Two services in a boundary, one calling the other.");
  });

  it("declares groups before the services that sit inside them", () => {
    const source = toMermaid(SPEC);
    const groupAt = source.indexOf("group zone(server)[your hosts]");
    const serviceAt = source.indexOf("service graph(server)[orchestrator] in zone");
    expect(groupAt).toBeGreaterThan(-1);
    expect(serviceAt).toBeGreaterThan(groupAt);
  });

  it("emits a service outside any group without an `in` clause", () => {
    expect(toMermaid(SPEC)).toContain("    service app(internet)[your app]");
  });

  it("writes sides and arrows, defaulting to R -> L and an arrow at the target", () => {
    const source = toMermaid(SPEC);
    expect(source).toContain("app:B --> T:graph");
    expect(source).toContain("graph:R -- L:db");
    const bare = toMermaid({
      title: "t",
      description: "d",
      services: [
        { id: "a", label: "A" },
        { id: "b", label: "B" },
      ],
      edges: [{ from: "a", to: "b" }],
    });
    expect(bare).toContain("a:R --> L:b");
  });

  it("orders a nested group's parent first even when the child is listed first", () => {
    const source = toMermaid({
      title: "t",
      description: "d",
      groups: [
        { id: "inner", label: "inner", parent: "outer" },
        { id: "outer", label: "outer" },
      ],
      services: [{ id: "a", label: "A", group: "inner" }],
      edges: [],
    });
    expect(source.indexOf("group outer[outer]")).toBeLessThan(
      source.indexOf("group inner[inner] in outer"),
    );
  });

  it("emits junctions and alignments only when the spec asks for them", () => {
    const source = toMermaid({
      title: "t",
      description: "d",
      services: [{ id: "a", label: "A" }],
      junctions: [{ id: "j1", group: "zone" }],
      edges: [],
      aligns: [{ axis: "row", ids: ["a", "b"] }],
    });
    expect(source).toContain("junction j1 in zone");
    expect(source).toContain("align row a b");
    expect(toMermaid(SPEC)).not.toContain("junction");
    expect(toMermaid(SPEC)).not.toContain("align ");
  });

  it("removes no icon syntax when a service declares none", () => {
    const source = toMermaid({
      title: "t",
      description: "d",
      services: [{ id: "a", label: "no icon" }],
      edges: [],
    });
    expect(source).toContain("    service a[no icon]");
    expect(source).not.toContain("()");
  });
});
