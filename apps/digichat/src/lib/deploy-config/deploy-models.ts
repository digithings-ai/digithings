/**
 * The digichat unconfigured-container model table — one definition, read from
 * `apps/digichat/config/digichat-deploy-models.json` (#5029).
 *
 * Why this file lives here and not in a consumer:
 *
 * The table used to be copied, byte for byte, into BOTH the server-side dev
 * default (`loader.ts`) and the browser-facing projection
 * (`client-projection.ts`). Two identical copies cannot drift without someone
 * noticing, and nothing failed when they did: every test asserted the literal
 * values, which both copies satisfied equally. So the only way to catch a
 * re-divergence is to assert the *structure* — that no consumer names a model —
 * which `deploy-models.test.ts` does.
 *
 * Why JSON rather than a generated TypeScript module: the ids must not be
 * string literals in code, and a generated `.ts` file would put them right back
 * in code under `src/`. A JSON import is inlined by the bundler, so this also
 * adds no runtime file read — the standalone image ships `apps/digichat/config`
 * anyway, but nothing here depends on that copy.
 *
 * `allowPicker` is deliberately NOT part of this table. It is a client feature
 * flag, not model vocabulary, and each consumer owns its own copy of it.
 */

import raw from "../../../config/digichat-deploy-models.json";

export interface DeployModelTable {
  /** Model the picker preselects. Always present in `available`. */
  default: string;
  /** Every model id an unconfigured container will offer. */
  available: string[];
}

const table = raw as DeployModelTable;

// Fail closed: a table whose default is not offered would render a picker
// pointing at a model the allowlist rejects, and the mismatch only surfaces at
// request time — far from the edit that caused it.
if (!table.available.includes(table.default)) {
  throw new Error(
    `digichat-deploy-models.json: default ${table.default} is not in available`,
  );
}

/**
 * The parsed JSON is copied rather than handed out by reference, so a consumer
 * cannot reach into the imported module object. Consumers still share this one
 * record — it is exported as a plain `string[]` to match `ModelsSchema` /
 * `DigichatClientModels`, which is why `Object.freeze` is not used here. Treat
 * it as read-only; the two consumers are the reason it exists.
 */
export const DEPLOY_DEFAULT_MODELS: DeployModelTable = {
  default: table.default,
  available: [...table.available],
};
