/**
 * The one node API a test in this package reaches for, declared locally.
 *
 * This package's tsconfig pins `types: ["react", "react-dom"]` so a browser
 * component cannot quietly reach for node globals; one stylesheet-contract
 * assertion in NavShell.render.test.tsx is no reason to widen that to all of
 * @types/node. Vite's `?raw` / `?inline` suffixes would avoid the import
 * entirely, but vitest runs with CSS processing off and both resolve to an
 * empty string — verified, not assumed.
 */
declare module "node:fs" {
  export function readFileSync(path: string | URL, encoding: "utf8"): string;
}
