// Minimal ambient types for the one YAML dependency the devkit CLI uses.
// js-yaml ships no bundled types; the devkit is bun-managed and outside the root
// npm workspaces, so it does not inherit @types/js-yaml from there.
declare module "js-yaml" {
  export function load(text: string): unknown;
  export function dump(value: unknown, options?: { lineWidth?: number; noRefs?: boolean }): string;
}
