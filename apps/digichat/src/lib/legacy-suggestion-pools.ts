/**
 * Public stand-in for `legacy-suggestion-pools.ts` (#6751). The live module
 * holds deployment data and stays private; the export writes this file at its
 * path. Tenants set `suggestions` in their document instead.
 */
export const LEGACY_TENANT_SUGGESTION_POOLS: Record<string, readonly string[]> = {};
