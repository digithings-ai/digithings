/**
 * Hand-written declarations for security-headers.mjs (the canonical
 * static-export header values, REM-077) so TypeScript consumers — currently
 * security-headers.test.ts — typecheck without converting the module that
 * scripts import as plain ESM.
 */
export declare const OLYMPUS_CSP: string;
export declare const OLYMPUS_SECURITY_HEADERS: ReadonlyArray<{ key: string; value: string }>;
