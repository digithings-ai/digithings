/** Tagged product releases named in the repository changelogs.
 *  digiquant itself ships on develop and has no product tag. */
export const TAGGED_RELEASES = [
  {
    product: "digichat",
    version: "2.4.0",
    date: "2026-09-29",
    href: "https://github.com/digithings-ai/digithings/compare/digichat-v2.3.2...digichat-v2.4.0",
  },
  {
    product: "digiskills",
    version: "0.2.1",
    date: "2026-08-15",
    href: "https://github.com/digithings-ai/digithings/compare/digiskills-v0.2.0...digiskills-v0.2.1",
  },
] as const;
