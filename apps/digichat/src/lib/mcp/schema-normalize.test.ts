import { describe, expect, it } from "vitest";
import catalog from "./__fixtures__/mcp-sdk-tool-schemas.json";
import {
  auditToolSchema,
  coerceToolArguments,
  normalizeToolSchema,
  normalizeToolsListResult,
  type JsonSchema,
} from "./schema-normalize";

type Tool = { name: string; inputSchema: JsonSchema };
const snapshots = catalog.snapshots as unknown as Record<string, Tool[]>;

/** The server-side check (DCE-152 `ToolArguments.Diagnose`): first non-null type wins. */
function serverAccepts(schema: JsonSchema, value: unknown): boolean {
  const t = schema.type;
  const lead = Array.isArray(t) ? (t as string[]).find((x) => x !== "null") : (t as string | undefined);
  if (lead === undefined) return true;
  switch (lead) {
    case "string":
      return typeof value === "string";
    case "integer":
    case "number":
      return typeof value === "number";
    case "boolean":
      return typeof value === "boolean";
    case "array":
      return Array.isArray(value);
    case "object":
      return typeof value === "object" && value !== null && !Array.isArray(value);
    default:
      return true;
  }
}

/** A value a model would plausibly send for a normalized property schema. */
function sampleFor(schema: JsonSchema): unknown {
  const t = schema.type;
  const lead = Array.isArray(t) ? (t as string[]).find((x) => x !== "null") : t;
  switch (lead) {
    case "integer":
      return 20;
    case "number":
      return 2.5;
    case "boolean":
      return true;
    case "array":
      return [];
    case "object":
      return {};
    default:
      return "x";
  }
}

function everyNode(schema: unknown, visit: (s: JsonSchema) => void): void {
  if (Array.isArray(schema)) return schema.forEach((s) => everyNode(s, visit));
  if (typeof schema !== "object" || schema === null) return;
  visit(schema as JsonSchema);
  for (const v of Object.values(schema)) everyNode(v, visit);
}

describe("normalizeToolSchema", () => {
  it("collapses the SDK's int? union to integer|null and drops its fake default", () => {
    expect(normalizeToolSchema({ type: ["string", "integer", "null"], default: 0 })).toEqual({
      type: ["integer", "null"],
    });
  });

  it("collapses number and boolean unions, nullable or not", () => {
    expect(normalizeToolSchema({ type: ["string", "number", "null"] })).toEqual({ type: ["number", "null"] });
    expect(normalizeToolSchema({ type: ["string", "boolean"] })).toEqual({ type: "boolean" });
    expect(normalizeToolSchema({ type: ["integer", "string", "number"] })).toEqual({ type: "number" });
  });

  it("keeps a null default on a collapsed nullable union", () => {
    expect(normalizeToolSchema({ type: ["string", "integer", "null"], default: null })).toEqual({
      type: ["integer", "null"],
      default: null,
    });
  });

  it("leaves unions it cannot collapse safely", () => {
    for (const type of [["string", "array"], ["string", "null"], ["object", "integer"], ["string", "boolean", "number"]]) {
      expect(normalizeToolSchema({ type })).toEqual({ type });
    }
  });

  it("collapses a primitive-only anyOf / oneOf", () => {
    expect(
      normalizeToolSchema({ anyOf: [{ type: "string" }, { type: "integer" }, { type: "null" }], description: "n" }),
    ).toEqual({ type: ["integer", "null"], description: "n" });
    expect(normalizeToolSchema({ oneOf: [{ type: "boolean" }, { type: "string" }] })).toEqual({ type: "boolean" });
    const structured = { anyOf: [{ type: "string" }, { type: "object", properties: {} }] };
    expect(normalizeToolSchema(structured)).toEqual(structured);
  });

  it("drops a default the type does not admit", () => {
    expect(normalizeToolSchema({ type: "string", default: null })).toEqual({ type: "string" });
    expect(normalizeToolSchema({ type: "array", items: { type: "string" }, default: null })).toEqual({
      type: "array",
      items: { type: "string" },
    });
    expect(normalizeToolSchema({ type: "integer", default: 1.5 })).toEqual({ type: "integer" });
    expect(normalizeToolSchema({ type: "boolean", default: false })).toEqual({ type: "boolean", default: false });
  });

  it("recurses into properties, items, anyOf branches and $defs", () => {
    const out = normalizeToolSchema({
      type: "object",
      properties: {
        page: { type: ["string", "integer", "null"], default: 0 },
        rows: { type: "array", items: { type: "object", properties: { n: { type: ["string", "number"] } } } },
        either: { anyOf: [{ type: "object", properties: { k: { type: ["string", "boolean", "null"] } } }, { type: "null" }] },
      },
      $defs: { Size: { type: ["string", "integer"], default: "big" } },
      additionalProperties: { type: ["string", "integer"] },
    }) as JsonSchema;
    expect(out).toEqual({
      type: "object",
      properties: {
        page: { type: ["integer", "null"] },
        rows: { type: "array", items: { type: "object", properties: { n: { type: "number" } } } },
        either: { anyOf: [{ type: "object", properties: { k: { type: ["boolean", "null"] } } }, { type: "null" }] },
      },
      $defs: { Size: { type: "integer" } },
      additionalProperties: { type: "integer" },
    });
  });

  it("maps numeric-string enum members onto a collapsed number type", () => {
    expect(normalizeToolSchema({ type: ["string", "integer"], enum: ["10", "20", "all"] })).toEqual({
      type: "integer",
      enum: [10, 20],
    });
  });

  it("never mutates its input", () => {
    const input = { type: "object", properties: { p: { type: ["string", "integer", "null"], default: 0 } } };
    const copy = structuredClone(input);
    normalizeToolSchema(input);
    expect(input).toEqual(copy);
  });

  it("rewrites every tool in a tools/list result and leaves other fields alone", () => {
    const result = {
      tools: [{ name: "t", description: "d", inputSchema: { type: "object", properties: { p: { type: ["string", "integer"] } } } }],
      nextCursor: "c",
    };
    expect(normalizeToolsListResult(result)).toEqual({
      tools: [{ name: "t", description: "d", inputSchema: { type: "object", properties: { p: { type: "integer" } } } }],
      nextCursor: "c",
    });
    expect(normalizeToolsListResult({ notTools: 1 })).toEqual({ notTools: 1 });
  });
});

describe("coerceToolArguments", () => {
  const original = {
    type: "object",
    properties: {
      pageSize: { type: ["string", "integer", "null"], default: 0 },
      marker: { type: "string", default: null },
      count: { type: "integer" },
      flag: { type: ["string", "boolean"] },
      nested: { type: "object", properties: { size: { type: ["string", "number"] } } },
      list: { type: "array", items: { type: ["string", "integer"] } },
      id: { type: "string" },
    },
    required: ["id"],
  };

  it("sends a number as the string the server's schema leads with", () => {
    expect(coerceToolArguments(original, { pageSize: 20, id: "a" })).toEqual({ pageSize: "20", id: "a" });
    expect(coerceToolArguments(original, { flag: true, id: "a" })).toEqual({ flag: "true", id: "a" });
  });

  it("leaves a value the server already leads with, and plain integers, alone", () => {
    expect(coerceToolArguments(original, { pageSize: "20", count: 5, id: "a" })).toEqual({
      pageSize: "20",
      count: 5,
      id: "a",
    });
  });

  it("omits an explicit null on an optional argument but keeps it on a required one", () => {
    expect(coerceToolArguments(original, { marker: null, pageSize: null, id: null })).toEqual({ id: null });
  });

  it("recurses into objects and arrays and passes unknown arguments through", () => {
    expect(coerceToolArguments(original, { nested: { size: 1.5 }, list: [1, "2"], extra: 3, id: "a" })).toEqual({
      nested: { size: "1.5" },
      list: ["1", "2"],
      extra: 3,
      id: "a",
    });
  });

  it("does not touch arguments when the schema is unusable", () => {
    expect(coerceToolArguments(undefined, { a: 1 })).toEqual({ a: 1 });
    expect(coerceToolArguments(original, "raw")).toBe("raw");
  });
});

describe("full tool catalog regression (DC-18)", () => {
  const expectedUnions: Record<string, string[]> = {
    master: [
      "get_collector_report_accounts.pageSize",
      "list_collector_reports.pageSize",
      "search_attachments.minSizeBytes",
    ],
    "feature-mcp-insights-phase1": [
      "get_archive_report_accounts.pageSize",
      "get_collection_points.pageSize",
      "get_collector_report_accounts.pageSize",
      "get_datamanagement_report_accounts.pageSize",
      "list_archive_reports.pageSize",
      "list_collector_reports.pageSize",
      "list_datamanagement_reports.pageSize",
      "search_attachments.minSizeBytes",
    ],
  };

  for (const [snapshot, tools] of Object.entries(snapshots)) {
    describe(snapshot, () => {
      it("finds exactly the known multi-type unions before normalizing", () => {
        const found = tools
          .flatMap((t) => auditToolSchema(t.inputSchema).map((f) => ({ ...f, tool: t.name })))
          .filter((f) => f.issue === "multi-type-union")
          .map((f) => `${f.tool}.${f.path}`)
          .sort();
        expect(found).toEqual(expectedUnions[snapshot]);
      });

      it("leaves no union, primitive anyOf or mismatched default in any tool", () => {
        for (const tool of tools) {
          const normalized = normalizeToolSchema(tool.inputSchema) as JsonSchema;
          expect(auditToolSchema(normalized), tool.name).toEqual([]);
          everyNode(normalized, (node) => {
            if (Array.isArray(node.type)) {
              expect((node.type as string[]).filter((t) => t !== "null").length, tool.name).toBe(1);
            }
          });
        }
      });

      it("turns every call a model makes against the normalized schema into one the server accepts", () => {
        for (const tool of tools) {
          const normalized = normalizeToolSchema(tool.inputSchema) as JsonSchema;
          const props = (normalized.properties ?? {}) as Record<string, JsonSchema>;
          const originalProps = (tool.inputSchema.properties ?? {}) as Record<string, JsonSchema>;
          const args = Object.fromEntries(Object.entries(props).map(([k, s]) => [k, sampleFor(s)]));
          const sent = coerceToolArguments(tool.inputSchema, args) as Record<string, unknown>;
          for (const [k, v] of Object.entries(sent)) {
            expect(serverAccepts(originalProps[k], v), `${tool.name}.${k}=${JSON.stringify(v)}`).toBe(true);
          }
        }
      });
    });
  }
});
