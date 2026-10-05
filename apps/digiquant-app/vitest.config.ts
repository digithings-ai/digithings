import path from 'node:path';
import { defineConfig } from 'vitest/config';

/**
 * digiquant-app Vitest config — node-environment, mirrors `apps/dashboard`
 * and `apps/digichat` so the three research frontends run the same way.
 *
 * It exists because `lib/block-age.test.ts` shipped without one. Without it
 * the window-age suite could not be executed by anything:
 *
 *   - `bun test` runs it, but `bun:test` has no `vi.setSystemTime`, so the
 *     timezone test that pins `todayYmd` to the reader's local calendar day
 *     ERRORS instead of running. 22 pass, 1 fail — and the one that dies is
 *     the load-bearing one.
 *   - `vitest run` could not even load the file: the tests import through the
 *     `@/` alias, which only `tsconfig.json` declares for Next, and Vitest
 *     does not read tsconfig paths.
 *
 * The `@/` alias below is the whole fix for the second case; it maps to the
 * same target Next resolves (`tsconfig.json` maps `@/*` -> `./*`).
 */
export default defineConfig({
  test: {
    environment: 'node',
    include: [
      'lib/**/*.test.ts',
      'lib/**/*.test.tsx',
      'components/**/*.test.ts',
      'components/**/*.test.tsx',
    ],
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, '.'),
    },
  },
});