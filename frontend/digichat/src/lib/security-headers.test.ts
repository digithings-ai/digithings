import { describe, expect, it } from "vitest";
import {
  DIGICHAT_APP_CSP,
  DIGICHAT_APP_SECURITY_HEADERS,
  DIGICHAT_EMBED_SECURITY_HEADERS,
  EMBED_FRAME_ANCESTORS,
  embedFrameAncestorsCsp,
} from "./security-headers";

describe("security-headers", () => {
  it("denies framing on the main app CSP", () => {
    expect(DIGICHAT_APP_CSP).toContain("frame-ancestors 'none'");
    expect(DIGICHAT_APP_CSP).toContain("default-src 'self'");
  });

  it("allows only marketing origins on embed frame-ancestors", () => {
    const csp = embedFrameAncestorsCsp();
    for (const origin of EMBED_FRAME_ANCESTORS) {
      expect(csp).toContain(origin);
    }
    expect(csp).not.toContain("'none'");
  });

  it("exports app and embed header sets", () => {
    expect(DIGICHAT_APP_SECURITY_HEADERS.some((h) => h.key === "X-Frame-Options")).toBe(
      true,
    );
    expect(
      DIGICHAT_EMBED_SECURITY_HEADERS.find((h) => h.key === "Content-Security-Policy")
        ?.value,
    ).toBe(embedFrameAncestorsCsp());
  });
});
