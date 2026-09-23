import { auth } from "@/auth";
import { ChatShell } from "@/components/chat-shell";
import { redirect } from "next/navigation";
import { clientConfigFromDeployment } from "@/lib/deploy-config";
import {
  getPrimaryDeployment,
  getDigichatConfig,
} from "@/lib/deploy-config/loader";
import { isFramedPresentation, skinOwnsPageChrome } from "@/lib/thread-skins";
import { HomeStockClient } from "./home-stock-client";

/**
 * Root `/` — chrome.mode from deployment config selects the presentation.
 * - embed (default): redirect to /embed (anonymous iframe surface)
 * - modal | sidebar: framed stock shell (launcher panel / docked panel, #4515)
 * - app + auth session: ChatShell (server persistence) or stock shell (memory/none)
 * - app + anonymous: stock shell against POST /api/chat without Auth.js wall
 */
export default async function Home() {
  let deployment;
  try {
    deployment = getPrimaryDeployment(getDigichatConfig());
  } catch {
    deployment = null;
  }
  const client = clientConfigFromDeployment(deployment);
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
