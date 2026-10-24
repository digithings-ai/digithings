/**
 * MCP tool-schema normalizer for agent runtimes that read a JSON Schema
 * `type` union by its FIRST member (DC-18).
 *
 * The .NET MCP SDK (ModelContextProtocol 0.3.x) publishes every `int?` /
 * `long?` / `double?` / `bool?` tool parameter as
 *
 *     { "type": ["string", "integer", "null"], "default": 0 }
 *
 * because its serializer reads numbers from strings. A model that sees that
 * union sends a number (correct), and a validator that only honours the first
 * member calls the number wrong. It also publishes every `string?` parameter
 * as `{ "type": "string", "default": null }` — a default its own type rejects.
 *
 * This module fixes the SHAPE, generically, for every tool on every MCP server
 * routed through it; nothing here names a tool or a parameter:
 *
 * - a union of `string` with one or more of integer / number / boolean
 *   collapses to the non-string primitive (+ `null` when it was nullable).
 *   `integer` + `number` together collapse to `number`;
 * - a primitive-only `anyOf` / `oneOf` (`[{type:"string"},{type:"integer"}]`)
 *   collapses the same way;
 * - a `default` that the (normalized) type does not admit is dropped, and a
 *   non-null default on a collapsed union is dropped too: the emitter could not
 *   express the parameter's real type, so its default (`0` for "default 15")
 *   is not evidence of anything;
 * - recursion covers properties, items / prefixItems, additionalProperties,
 *   patternProperties, anyOf / oneOf / allOf, not, and $defs / definitions.
 *
 * Any other union (e.g. `["string","array"]`) is left alone — collapsing it
 * would drop a shape the server really accepts.
 *
 * The other half is {@link coerceToolArguments}: what the model sends against
 * the normalized schema is reshaped to what the server's ORIGINAL schema leads
 * with, so a server that validates by first member too (it does, DCE-152) gets
 * a value it accepts.
 */

export type JsonSchema = Record<string, unknown>;
type Json = unknown;

const NON_STRING_PRIMITIVES = new Set(["integer", "number", "boolean"]);

function isObject(value: Json): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** The collapsed primitive for a string+primitive union, or null when the union is not that shape. */
function collapseUnion(types: readonly string[]): { type: string; nullable: boolean } | null {
  const nullable = types.includes("null");
  const nonNull = [...new Set(types.filter((t) => t !== "null"))];
  if (nonNull.length < 2 || !nonNull.includes("string")) return null;
  const others = nonNull.filter((t) => t !== "string");
  if (others.length === 0 || !others.every((t) => NON_STRING_PRIMITIVES.has(t))) return null;
  if (others.includes("boolean") && others.length > 1) return null; // boolean|number: no single answer
  const type = others.includes("number") ? "number" : others[0];
  return { type, nullable };
}

function typesOf(schema: JsonSchema): string[] | null {
  const t = schema.type;
  if (typeof t === "string") return [t];
  if (Array.isArray(t) && t.every((x) => typeof x === "string")) return t as string[];
  return null;
}

function admits(types: readonly string[], value: Json): boolean {
  if (value === null) return types.includes("null");
  if (typeof value === "boolean") return types.includes("boolean");
  if (typeof value === "number") {
    return types.includes("number") || (types.includes("integer") && Number.isInteger(value));
  }
  if (typeof value === "string") return types.includes("string");
  if (Array.isArray(value)) return types.includes("array");
  if (isObject(value)) return types.includes("object");
  return false;
}

/** `anyOf: [{type:"string"},{type:"integer"},{type:"null"}]` → its type list, else null. */
const SIMPLE_BRANCH_KEYS = new Set(["type", "description", "title", "format", "pattern"]);
function primitiveBranchTypes(branches: Json): string[] | null {
  if (!Array.isArray(branches) || branches.length < 2) return null;
  const out: string[] = [];
  for (const branch of branches) {
    if (!isObject(branch) || typeof branch.type !== "string") return null;
    if (!Object.keys(branch).every((k) => SIMPLE_BRANCH_KEYS.has(k))) return null;
    out.push(branch.type);
  }
  return out;
}

const SCHEMA_MAP_KEYS = ["properties", "patternProperties", "$defs", "definitions"] as const;
const SCHEMA_LIST_KEYS = ["anyOf", "oneOf", "allOf", "prefixItems"] as const;
const SCHEMA_ONE_KEYS = ["additionalProperties", "not", "contains", "propertyNames"] as const;

/** A normalized deep copy of `schema`. Never mutates its input. */
export function normalizeToolSchema(schema: Json): Json {
  if (Array.isArray(schema)) return schema.map(normalizeToolSchema);
  if (!isObject(schema)) return schema;
  const out: JsonSchema = { ...schema };

  let collapsed = false;
  const listed = typesOf(out);
  if (listed && Array.isArray(out.type)) {
    const c = collapseUnion(listed);
    if (c) {
      out.type = c.nullable ? [c.type, "null"] : c.type;
      collapsed = true;
    }
  }
  for (const key of ["anyOf", "oneOf"] as const) {
    if (out.type !== undefined) break;
    const branchTypes = primitiveBranchTypes(out[key]);
    const c = branchTypes && collapseUnion(branchTypes);
    if (c) {
      delete out[key];
      out.type = c.nullable ? [c.type, "null"] : c.type;
      collapsed = true;
    }
  }

  const types = typesOf(out);
  if ("default" in out && types) {
    const value = out.default;
    if (!admits(types, value) || (collapsed && value !== null)) delete out.default;
  }
  if (collapsed && Array.isArray(out.enum) && types) {
    // A numeric-string enum on what is now a number: keep the members it still admits.
    const kept = out.enum
      .map((v) => (typeof v === "string" && v.trim() !== "" && Number.isFinite(Number(v)) ? Number(v) : v))
      .filter((v) => admits(types, v));
    if (kept.length > 0) out.enum = kept;
    else delete out.enum;
  }

  for (const key of SCHEMA_MAP_KEYS) {
    const map = out[key];
    if (isObject(map)) {
      out[key] = Object.fromEntries(Object.entries(map).map(([k, v]) => [k, normalizeToolSchema(v)]));
    }
  }
  for (const key of SCHEMA_LIST_KEYS) {
    if (Array.isArray(out[key])) out[key] = (out[key] as Json[]).map(normalizeToolSchema);
  }
  for (const key of SCHEMA_ONE_KEYS) {
    if (isObject(out[key])) out[key] = normalizeToolSchema(out[key]);
  }
  if (out.items !== undefined) out.items = normalizeToolSchema(out.items);
  return out;
}

/** A `tools/list` result with every tool's `inputSchema` normalized. */
export function normalizeToolsListResult(result: Json): Json {
  if (!isObject(result) || !Array.isArray(result.tools)) return result;
  return {
    ...result,
    tools: result.tools.map((tool) =>
      isObject(tool) && tool.inputSchema !== undefined
        ? { ...tool, inputSchema: normalizeToolSchema(tool.inputSchema) }
        : tool,
    ),
  };
}

/** First non-null member of the server's ORIGINAL declared type. */
function leadingType(schema: JsonSchema): string | null {
  const types = typesOf(schema);
  return types?.find((t) => t !== "null") ?? null;
}

function requiredOf(schema: JsonSchema): Set<string> {
  return new Set(Array.isArray(schema.required) ? schema.required.filter((x): x is string => typeof x === "string") : []);
}

function coerceValue(original: JsonSchema | undefined, value: Json): Json {
  if (!original) return value;
  if (isObject(value) && isObject(original.properties)) {
    return coerceObject(original, value);
  }
  if (Array.isArray(value) && isObject(original.items)) {
    return value.map((v) => coerceValue(original.items as JsonSchema, v));
  }
  const types = typesOf(original);
  const lead = leadingType(original);
  // Only reshape a scalar the original union really accepts as a string: the
  // server leads with "string" and also lists the value's own kind.
  if (lead === "string" && types && (typeof value === "number" || typeof value === "boolean")) {
    if (admits(types, value)) return String(value);
  }
  return value;
}

function coerceObject(original: JsonSchema, args: Record<string, unknown>): Record<string, unknown> {
  const properties = isObject(original.properties) ? (original.properties as Record<string, JsonSchema>) : {};
  const required = requiredOf(original);
  const out: Record<string, unknown> = {};
  for (const [name, value] of Object.entries(args)) {
    // An explicit null on an optional argument means "not given": omit it, so
    // the server applies its own default instead of judging a null.
    if (value === null && !required.has(name)) continue;
    out[name] = coerceValue(isObject(properties[name]) ? properties[name] : undefined, value);
  }
  return out;
}

/**
 * Reshape call arguments, produced against the normalized schema, into what the
 * server's ORIGINAL `inputSchema` leads with. Unknown arguments pass through.
 */
export function coerceToolArguments(originalInputSchema: Json, args: Json): Json {
  if (!isObject(originalInputSchema) || !isObject(args)) return args;
  return coerceObject(originalInputSchema, args);
}

/** One finding per parameter whose shape the normalizer changes. */
export interface SchemaFinding {
  path: string;
  issue: "multi-type-union" | "primitive-anyof" | "default-mismatch";
  before: Json;
}

/** Audit a schema without changing it — the regression test pins this list. */
export function auditToolSchema(schema: Json, path = ""): SchemaFinding[] {
  if (!isObject(schema)) return [];
  const findings: SchemaFinding[] = [];
  const types = typesOf(schema);
  if (types && Array.isArray(schema.type) && collapseUnion(types)) {
    findings.push({ path: path || "<root>", issue: "multi-type-union", before: schema.type });
  }
  for (const key of ["anyOf", "oneOf"] as const) {
    const bt = primitiveBranchTypes(schema[key]);
    if (bt && collapseUnion(bt)) findings.push({ path: path || "<root>", issue: "primitive-anyof", before: bt });
  }
  if ("default" in schema && types && !admits(types, schema.default)) {
    findings.push({ path: path || "<root>", issue: "default-mismatch", before: schema.default });
  }
  if (isObject(schema.properties)) {
    for (const [k, v] of Object.entries(schema.properties)) {
      findings.push(...auditToolSchema(v, path ? `${path}.${k}` : k));
    }
  }
  if (isObject(schema.items)) findings.push(...auditToolSchema(schema.items, `${path}[]`));
  for (const key of SCHEMA_LIST_KEYS) {
    const list = schema[key];
    if (Array.isArray(list)) list.forEach((b, i) => findings.push(...auditToolSchema(b, `${path}<${key}${i}>`)));
  }
  return findings;
}
