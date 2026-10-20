import path from 'node:path';
import { defineConfig } from 'vitest/config';

/**
 * research frontend Vitest config — node-environment, mirrors the digichat setup
 * (`apps/digichat/vitest.config.ts`). Tests live next to the code under
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
    include: [
      'lib/**/*.test.ts',
      'lib/**/*.test.tsx',
      'components/**/*.test.ts',
      'components/**/*.test.tsx',
      'app/**/*.test.ts',
      'app/**/*.test.tsx',
    ],
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
      // Subpath first: Vite alias matching is prefix-based, so the bare entry
      // would swallow `@digithings/ui/ui` (resolving it to `…/index.ts/ui`).
      '@digithings/ui/ui': path.resolve(__dirname, '../../packages/ui/src/ui/index.ts'),
      '@digithings/ui': path.resolve(__dirname, '../../packages/ui/src/index.ts'),
    },
  },
});
