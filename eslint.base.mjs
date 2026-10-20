// Shared flat-config building blocks for every digithings Next.js app (DIG-3396).
//
// Flat config resolves from the working directory, so each app keeps its own
// thin `eslint.config.mjs` — but those files only call the helpers below and
// add ignores/rules that are genuinely app-specific. The expanded config is
// identical to the previous per-app copies; behaviour is unchanged.
//
// Import with a relative path, e.g. `import { nextApp } from "../../eslint.base.mjs";`.
// A relative import needs no workspace dependency wiring and always resolves
// to the checkout being linted.

import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import reactHooks from "eslint-plugin-react-hooks";

// Ignores every Next.js app needs: build output plus the generated
// `next-env.d.ts` (linting it only re-reports tsc's job).
export const nextBuildIgnores = [".next/**", ".next-*/**", "out/**", "build/**", "next-env.d.ts"];

// Full Next.js app preset: core-web-vitals + (optionally) TypeScript + build
// ignores, plus any extra app-specific ignore patterns.
//
// `typescript: false` exists for one app only (dashboard predates the TS
// preset); new apps use the default. Do not flip dashboard to `true` in a
// config refactor — that enables new rules and belongs in its own PR.
// Repo-split boundary (DIG-3695): apps import shared code only through
// package exports — never by relative path into `packages/*/src`,
// `clients/*`, or a sibling app. Relative imports inside the app itself
// (`@/…`, `./…`) are unaffected.
const packageBoundaryRules = {
  "no-restricted-imports": [
    "error",
    {
      patterns: [
        {
          group: [
            "../../packages/*/src",
            "../../packages/*/src/**",
            "../../../packages/*/src",
            "../../../packages/*/src/**",
            "../../../../packages/*/src",
            "../../../../packages/*/src/**",
          ],
          message: "Import via the package exports instead (e.g. `@digithings/ui/chat/stock`), not `packages/*/src` — see DIG-3695.",
        },
        {
          group: ["../../../clients/*", "../../../../clients/*", "../../../../../clients/*"],
          message: "Import via the package exports instead (e.g. `digiquant-tui/catalog`), not a relative `clients/*` path — see DIG-3695.",
        },
        {
          // Code only: config JSON reads (e.g. digichat-deploy-models.json, deliberately
          // owned by digichat per #5029 with fail-closed consumers) stay where they are.
          group: ["../../dashboard/src/**", "../../../dashboard/src/**", "../../digithings-web/src/**", "../../../digithings-web/src/**", "../../digichat/src/**", "../../../digichat/src/**"],
          message: "Sibling-app imports are not allowed: move the shared module into a package and import it via exports — see DIG-3695.",
        },
      ],
    },
  ],
};

export function nextApp(extraIgnores = [], { typescript = true } = {}) {
  return defineConfig([
    ...nextVitals,
    ...(typescript ? nextTs : []),
    { rules: { ...packageBoundaryRules } },
    globalIgnores([...nextBuildIgnores, ...extraIgnores]),
  ]);
}

// TypeScript-only preset for shared packages (no Next.js pages/router, so
// core-web-vitals does not apply). Lets `packages/*` run `eslint .` under
// the same TS rules as the apps.
//
// The react-hooks plugin is REGISTERED but none of its rules are enabled:
// package sources already carry disable directives naming those rules, and
// an unregistered name is a hard error. Enabling the rules themselves is a
// separate PR (85 findings on first measurement) — this preset only stops
// the directives from erroring. Unused-directive reporting stays off so the
// directives read as documentation, not noise.
export function tsLib(extraIgnores = []) {
  return defineConfig([
    ...nextTs,
    {
      plugins: { "react-hooks": reactHooks },
      linterOptions: { reportUnusedDisableDirectives: "off" },
    },
    globalIgnores(["dist/**", "build/**", "next-env.d.ts", ...extraIgnores]),
  ]);
}
