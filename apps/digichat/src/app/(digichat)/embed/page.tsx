/**
 * /embed — thin compat shell (single-route plan, Step 3).
 *
 * Renders the shared embed route shell, so /embed and /?mode=embed serve
 * byte-identical HTML. The tenant verify + first-paint seeding live in
 * `../embed-route-shell.tsx`. Compat redirect + edge rewrite = Step 5;
 * deletion = Step 6.
 */
import EmbedRouteShell from "../embed-route-shell";

export const dynamic = "force-dynamic";

export default async function EmbedPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  return <EmbedRouteShell params={await searchParams} />;
}
