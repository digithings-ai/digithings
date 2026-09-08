/**
 * SSR smoke for <SocialRow/>: the quiet company-profile utility row.
 * Live accounts only (GitHub, X, LinkedIn) — never Discord, never a Connect
 * list. Every profile is an external .btn-icon link, same grammar as the
 * NavShell GitHub slot.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { DIGITHINGS_SOCIALS, SocialRow } from "./SocialRow";

describe("DIGITHINGS_SOCIALS", () => {
  it("lists only the live GitHub, X, and LinkedIn profiles", () => {
    expect(DIGITHINGS_SOCIALS.map((p) => p.network)).toEqual(["github", "x", "linkedin"]);
    expect(DIGITHINGS_SOCIALS.map((p) => p.href)).toEqual([
      "https://github.com/digithings-ai/digithings",
      "https://x.com/digithingsai",
      "https://www.linkedin.com/company/digithingsai/",
    ]);
  });

  it("does not invent Discord or other networks", () => {
    const blob = JSON.stringify(DIGITHINGS_SOCIALS).toLowerCase();
    expect(blob).not.toContain("discord");
    expect(blob).not.toContain("slack");
    expect(blob).not.toContain("youtube");
  });
});

describe("SocialRow", () => {
  it("renders the default profiles as external icon buttons", () => {
    const html = renderToStaticMarkup(<SocialRow />);
    expect(html).toContain('aria-label="Company profiles"');
    expect(html).toContain("social-row");
    expect(html).toContain('href="https://github.com/digithings-ai/digithings"');
    expect(html).toContain('href="https://x.com/digithingsai"');
    expect(html).toContain('href="https://www.linkedin.com/company/digithingsai/"');
    expect(html).toContain('aria-label="digithings on GitHub"');
    expect(html).toContain('aria-label="digithings on X"');
    expect(html).toContain('aria-label="digithings on LinkedIn"');
    expect(html.match(/class="btn-icon"/g)).toHaveLength(3);
  });

  it("opens every profile in a new tab with noopener noreferrer", () => {
    const html = renderToStaticMarkup(<SocialRow />);
    expect(html.match(/target="_blank"/g)).toHaveLength(3);
    expect(html.match(/rel="noopener noreferrer"/g)).toHaveLength(3);
  });

  it("accepts a custom profiles list", () => {
    const html = renderToStaticMarkup(
      <SocialRow
        aria-label="Profiles"
        profiles={[
          {
            network: "github",
            href: "https://github.com/example/repo",
            label: "example on GitHub",
          },
        ]}
      />,
    );
    expect(html).toContain('aria-label="Profiles"');
    expect(html).toContain('href="https://github.com/example/repo"');
    expect(html).not.toContain("linkedin.com");
    expect(html).not.toContain("discord");
  });

  it("does not render Discord", () => {
    const html = renderToStaticMarkup(<SocialRow />);
    expect(html.toLowerCase()).not.toContain("discord");
  });
});
