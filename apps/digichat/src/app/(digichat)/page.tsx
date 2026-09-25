import { auth } from "@/auth";
import { ChatShell } from "@/components/chat-shell";
import { notFound, redirect } from "next/navigation";
import type { Metadata } from "next";
import { resolveRouteClientConfig } from "@/lib/route-client-config";
import {
  getPrimaryDeployment,
  getDigichatConfig,
} from "@/lib/deploy-config/loader";
import {
  isFramedPresentation,
  skinOwnsPageChrome,
} from "@digithings/ui/chat/skins";
import { HomeStockClient } from "./home-stock-client";
import { BaselineClient } from "../(baseline)/baseline/baseline-client";
import EmbedRouteShell from "./embed-route-shell";
import { RouteMenu } from "./route-menu";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<Metadata> {
  const params = await searchParams;
  if (params.mode !== "embed" && params.mode !== "catalog") return {};
  if (params.mode === "embed")
    return {
      title: "digichat",
      description: "Embedded digichat preview.",
      robots: { index: false, follow: false },
    };
  return { robots: { index: false, follow: false } };
}

/**
 * Root `/` — the single digichat route (single-route plan, Step 3 + menu root).
 * `?mode=` selects the surface; bare `/` renders the menu (no chat).
 * - embed: tenant iframe surface (same shell as /embed)
 * - catalog: skin catalog (same client as /baseline; production → notFound)
 * - product: chrome.mode from deployment config selects presentation:
 *   - embed (default): redirect to /embed (anonymous iframe surface)
 *   - modal | sidebar: framed stock shell (launcher panel / docked panel, #4515)
 *   - app + auth session: ChatShell (server persistence) or stock shell (memory/none)
 *   - app + anonymous: stock shell against POST /api/chat without Auth.js wall
 */
export default async function Home({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const routeMode =
    params.mode === "embed"
      ? "embed"
      : params.mode === "catalog"
        ? "catalog"
        : params.mode === "product"
          ? "product"
          : "menu";

  if (routeMode === "menu") return <RouteMenu />;

  if (routeMode === "catalog") {
    if (process.env.NODE_ENV === "production") {
      notFound();
    }
    return (
      <div data-route-mode="catalog" className="contents">
        <BaselineClient />
      </div>
    );
  }

  if (routeMode === "embed") {
    return <EmbedRouteShell params={params} />;
  }

  let deployment;
  try {
    deployment = getPrimaryDeployment(getDigichatConfig());
  } catch {
    deployment = null;
  }
  const client = resolveRouteClientConfig({ mode: "product", deployment });
  const mode = client.chrome.mode;
  const layoutSkin = skinOwnsPageChrome(client.chrome.skin);
  // modal and sidebar are real in-app surfaces now; only `embed` bounces out.
  // A layout skin owns `/` regardless of mode, so it is never "framed".
  const framed = isFramedPresentation(mode) && !layoutSkin;

  if (!layoutSkin && mode === "embed") {
    redirect("/embed");
  }

  // Layout templates (docs / dashboard / expo) own `/` even when chrome.mode
  // is embed — wrapping them in ChatShell or bouncing to /embed strips the page.
  if (layoutSkin) {
    if (client.auth === "session") {
      const session = await auth();
      if (!session?.user) {
        redirect("/embed");
      }
      return (
        <HomeStockClient clientConfig={client} userId={session.user.id} />
      );
    }
    return <HomeStockClient clientConfig={client} />;
  }

  // chrome.mode === "app" (or a framed modal/sidebar mount)
  if (client.auth === "session") {
    const session = await auth();
    if (!session?.user) {
      redirect("/embed");
    }
    // ChatShell is the full-page authenticated surface; a framed mode mounts
    // the stock shell inside its frame instead.
    if (client.persistence === "server" && !framed) {
      return (
        <ChatShell
          userId={session.user.id}
          userEmail={session.user.email}
          displayName={session.user.name}
          clientConfig={client}
        />
      );
    }
    return (
      <HomeStockClient
        clientConfig={client}
        userId={session.user.id}
      />
    );
  }

  // anonymous app
  return <HomeStockClient clientConfig={client} />;
}
