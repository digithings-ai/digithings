/**
 * Layer a digichat overlay onto defaults.yaml.
 *
 * Objects merge. Arrays replace, except `embedHosts`, which unions.
 * `null` deletes a key. A backend whose `type` differs replaces the whole
 * backend. A host the base does not have starts from the house deployment,
 * then the overlay. `parseDigichatConfig` stays free of this: client bundles
 * import the schema, and this module does not read the disk.
 */

export function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const UNION_ARRAY_KEYS = new Set(["embedHosts"]);

export function deepMergeConfig(base: unknown, overlay: unknown, path = ""): unknown {
  if (overlay === null) return undefined;
  if (Array.isArray(overlay)) {
    const key = path.split(".").pop() ?? "";
    if (UNION_ARRAY_KEYS.has(key)) {
      const prior = Array.isArray(base) ? base.filter((item) => typeof item === "string") : [];
      const extra = overlay.filter((item): item is string => typeof item === "string");
      return [...new Set([...prior, ...extra])];
    }
    return overlay.map((item) => item);
  }
  if (!isPlainObject(overlay)) return overlay;
  const key = path.split(".").pop() ?? path;
  if (
    key === "backend" &&
    isPlainObject(base) &&
    typeof overlay.type === "string" &&
    overlay.type !== base.type
  ) {
    return overlay;
  }
  const start: Record<string, unknown> = isPlainObject(base) ? { ...base } : {};
  for (const [child, value] of Object.entries(overlay)) {
    if (child === "extends") continue;
    const childPath = path ? `${path}.${child}` : child;
    if (value === null) {
      delete start[child];
      continue;
    }
    const merged = deepMergeConfig(start[child], value, childPath);
    if (merged === undefined) delete start[child];
    else start[child] = merged;
  }
  return start;
}

/**
 * Hosts in an overlay replace the host map. Each host starts from the house
 * deployment when the base has no entry for that hostname.
 */
export function mergeHostMap(
  prototype: unknown,
  overlayHosts: Record<string, unknown>,
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [host, overlay] of Object.entries(overlayHosts)) {
    const start = isPlainObject(prototype) ? structuredClone(prototype) : {};
    const merged = deepMergeConfig(start, overlay, `hosts.${host}`);
    if (merged !== undefined) out[host] = merged;
  }
  return out;
}

export function expandExtendsDocument(
  doc: unknown,
  read: (name: string) => unknown,
  stack: string[] = [],
): unknown {
  if (!isPlainObject(doc) || typeof doc.extends !== "string") return doc;
  const name = doc.extends.trim();
  if (!name) throw new Error("extends: empty");
  if (name.includes("..") || name.startsWith("/") || name.includes("\\")) {
    throw new Error(`extends: ${name} is not a config name`);
  }
  if (stack.includes(name)) {
    throw new Error(`extends cycle: ${[...stack, name].join(" -> ")}`);
  }
  const base = expandExtendsDocument(read(name), read, [...stack, name]);
  if (!isPlainObject(base)) {
    throw new Error(`extends ${name} did not resolve to a mapping`);
  }
  const { hosts, ...rest } = doc;
  const merged = deepMergeConfig(base, rest, "") as Record<string, unknown>;
  if (hosts === null) {
    delete merged.hosts;
  } else if (isPlainObject(hosts)) {
    const prototype = isPlainObject(base.deployment) ? base.deployment : merged.deployment;
    merged.hosts = mergeHostMap(prototype, hosts);
  }
  delete merged.extends;
  return merged;
}
