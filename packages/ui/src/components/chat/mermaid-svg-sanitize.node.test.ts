/**
 * `sanitizeMermaidSvg` with no DOM — the SSR / plain-Node half of the contract.
 *
 * The default vitest environment (node) has no `window`, so DOMPurify cannot
 * sanitize. The helper must fail closed (return "") rather than hand the raw
 * renderer output to `dangerouslySetInnerHTML`; the client render fills the
 * diagram once a DOM exists.
 */
import { describe, expect, it } from "vitest";

import { sanitizeMermaidSvg } from "./sanitize-mermaid-svg";

describe("sanitizeMermaidSvg (no DOM)", () => {
  it("fails closed instead of passing raw SVG through", () => {
    expect(sanitizeMermaidSvg('<svg><script>alert(1)</script></svg>')).toBe("");
  });
});
