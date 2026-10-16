/** Tagged product releases named in the repository changelogs: only versions with a
 *  pushed `<product>-vX.Y.Z` tag. digichat 2.4.0 is in the changelog but untagged.
 *  digiquant itself ships on develop and has no product tag. */
export const TAGGED_RELEASES = [
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
