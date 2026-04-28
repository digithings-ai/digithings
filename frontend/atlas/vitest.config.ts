import path from 'node:path';
import { defineConfig } from 'vitest/config';

/**
 * Atlas frontend Vitest config — node-environment, mirrors the digichat setup
 * (`frontend/digichat/vitest.config.ts`). Tests live next to the code under
 * `lib/` and `components/`.
 *
 * `tsconfig.json` declares `jsx: "preserve"` for Next.js, which Vitest cannot
 * consume directly. We override the OXC transformer (Vitest 4's default) to
 * compile JSX automatically so `.tsx` files import cleanly under the test
 * runner.
 */
export default defineConfig({
  test: {
    environment: 'node',
    include: ['lib/**/*.test.ts', 'lib/**/*.test.tsx', 'components/**/*.test.tsx'],
    // OXC transformer config — mirrors Vitest's default but pins JSX runtime.
    // See https://vitest.dev/config/#oxc
  },
  oxc: {
    jsx: {
      runtime: 'automatic',
      importSource: 'react',
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, '.'),
    },
  },
});
