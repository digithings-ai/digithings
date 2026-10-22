/** Tagged product releases named in the repository changelogs: only versions with a
 *  pushed `<product>-vX.Y.Z` tag. digichat 2.4.0 is in the changelog but untagged;
 *  2.6.7 is the OCC-embed-fix release, tagged at its develop-to-main
 *  promotion commit, as 2.6.0-2.6.6 were; 2.6.6 was the take-the-chat-with-you release.
 *  digiquant itself ships on develop and has no product tag.
 *  Each href spans the previous tagged release of that product to this one, the same
 *  range the product changelog heading names. */
export const TAGGED_RELEASES = [
  {
    product: "digichat",
    version: "2.6.7",
    date: "2026-10-22",
    href: "https://github.com/digithings-ai/digithings/compare/digichat-v2.6.6...digichat-v2.6.7",
  },
  {
    product: "digichat",
    version: "2.6.6",
    date: "2026-10-21",
    href: "https://github.com/digithings-ai/digithings/compare/digichat-v2.6.5...digichat-v2.6.6",
  },
  {
    product: "digichat",
    version: "2.6.5",
    date: "2026-10-21",
    href: "https://github.com/digithings-ai/digithings/compare/digichat-v2.6.4...digichat-v2.6.5",
  },
  {
    product: "digichat",
    version: "2.6.4",
    date: "2026-10-21",
    href: "https://github.com/digithings-ai/digithings/compare/digichat-v2.6.3...digichat-v2.6.4",
  },
  {
    product: "digichat",
    version: "2.6.3",
    date: "2026-10-21",
    href: "https://github.com/digithings-ai/digithings/compare/digichat-v2.6.2...digichat-v2.6.3",
  },
  {
    product: "digichat",
    version: "2.6.2",
    date: "2026-10-21",
    href: "https://github.com/digithings-ai/digithings/compare/digichat-v2.6.1...digichat-v2.6.2",
  },
  {
    product: "digichat",
    version: "2.6.1",
    date: "2026-10-20",
    href: "https://github.com/digithings-ai/digithings/compare/digichat-v2.6.0...digichat-v2.6.1",
  },
  {
    product: "digichat",
    version: "2.6.0",
    date: "2026-10-20",
    href: "https://github.com/digithings-ai/digithings/compare/digichat-v2.5.1...digichat-v2.6.0",
  },
  {
    product: "digichat",
    version: "2.5.1",
    date: "2026-10-19",
    href: "https://github.com/digithings-ai/digithings/compare/digichat-v2.5.0...digichat-v2.5.1",
  },
  {
    product: "digichat",
    version: "2.3.2",
    date: "2026-09-21",
    href: "https://github.com/digithings-ai/digithings/compare/digichat-v2.3.1...digichat-v2.3.2",
  },
  {
    product: "digiskills",
    version: "0.2.1",
    date: "2026-08-15",
    href: "https://github.com/digithings-ai/digithings/compare/digiskills-v0.2.0...digiskills-v0.2.1",
  },
] as const;
