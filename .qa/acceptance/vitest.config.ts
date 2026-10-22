import path from 'node:path';

import { defineConfig } from 'vitest/config';

/**
 * QA acceptance kit for DIG-5204 (QA Engineer seat).
 *
 * The kit runs against the repository root so it can read both sides of the
 * contract at once: the producer under `clients/digichat-tui/` and the consumer
 * under `apps/dashboard/`. It is a local eval artifact, not product code.
 */

const REPO_ROOT = path.resolve(__dirname, '../..');
const DASHBOARD = path.resolve(REPO_ROOT, 'apps/dashboard');

export default defineConfig({
  root: REPO_ROOT,
  test: {
    environment: 'node',
    include: ['.qa/acceptance/**/*.test.ts'],
  },
  oxc: {
    jsx: {
      runtime: 'automatic',
      importSource: 'react',
    },
  },
  resolve: {
    alias: {
      '@': DASHBOARD,
      '@digithings/ui/ui': path.resolve(REPO_ROOT, 'packages/ui/src/ui/index.ts'),
      '@digithings/ui/lib/stub-payload': path.resolve(
        REPO_ROOT,
        'packages/ui/src/lib/stub-payload.ts',
      ),
      '@digithings/catalog/page-context-sanitize': path.resolve(
        REPO_ROOT,
        'packages/catalog/src/page-context-sanitize.ts',
      ),
      '@digithings/ui': path.resolve(REPO_ROOT, 'packages/ui/src/index.ts'),
    },
  },
});
