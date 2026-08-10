// Extends vitest's `expect` with DOM matchers (toBeInTheDocument, etc.) for
// React component tests such as language-select.test.tsx. Opting a test file
// into a real DOM goes through the per-file `// @vitest-environment happy-dom`
// pragma (vitest 4 removed environmentMatchGlobs) — this file only wires the
// matcher extension, which is a no-op for the plain node-environment tests.
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// `test.globals` is off (matches the rest of the repo's explicit-import
// style), so Testing Library's auto-cleanup never registers on its own —
// without this, DOM trees from earlier tests in the same file stay mounted
// and cause duplicate-role query failures in later tests.
afterEach(() => {
  cleanup();
});
