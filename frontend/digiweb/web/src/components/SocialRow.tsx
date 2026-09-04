/**
 * SocialRow — a quiet utility row of company-profile icon buttons.
 * Same borderless `.btn-icon` grammar as the NavShell GitHub slot: radius 0,
 * no fill, ink-mute → ink, phosphor (`--accent`) only on :focus-visible.
 * Not a marketing share bar. The primitive carries no Discord (that network
 * does not exist for the company); default `DIGITHINGS_SOCIALS` is the live
 * GitHub / X / LinkedIn set. Pass `profiles` to retarget; the row never
 * invents networks.
 *
 * Dress lives in styles/nav-shell.css (already imported wherever NavShell
 * is), so a contact band or footer can reuse the buttons without a second
 * sheet.
 */
import type { ReactNode } from "react";

import { GitHubGlyph, LinkedInGlyph, XGlyph } from "./icons";

export type SocialNetwork = "github" | "x" | "linkedin";

export type SocialProfile = {
  network: SocialNetwork;
  href: string;
  label: string;
};

/** Live company profiles only. Do not add networks we do not run. */
export const DIGITHINGS_SOCIALS: readonly SocialProfile[] = [
  {
    network: "github",
    href: "https://github.com/digithings-ai/digithings",
    label: "digithings on GitHub",
  },
  {
    network: "x",
    href: "https://x.com/digithingsai",
    label: "digithings on X",
  },
  {
    network: "linkedin",
    href: "https://www.linkedin.com/company/digithingsai/",
    label: "digithings on LinkedIn",
  },
];

export type SocialRowProps = {
  profiles?: readonly SocialProfile[];
  "aria-label"?: string;
  className?: string;
};

function SocialGlyph({ network }: { network: SocialNetwork }): ReactNode {
  switch (network) {
    case "github":
      return <GitHubGlyph />;
    case "x":
      return <XGlyph />;
    case "linkedin":
      return <LinkedInGlyph />;
    default: {
      const _exhaustive: never = network;
      return _exhaustive;
    }
  }
}

export function SocialRow({
  profiles = DIGITHINGS_SOCIALS,
  "aria-label": ariaLabel = "Company profiles",
  className,
}: SocialRowProps) {
  return (
    <nav className={className ? `social-row ${className}` : "social-row"} aria-label={ariaLabel}>
      {profiles.map((profile) => (
        <a
          key={profile.network}
          className="btn-icon"
          href={profile.href}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={profile.label}
        >
          <SocialGlyph network={profile.network} />
        </a>
      ))}
    </nav>
  );
}
