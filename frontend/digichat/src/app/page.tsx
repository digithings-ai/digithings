import { auth } from "@/auth";
import { isRootAuthRequired } from "@/lib/root-auth";
import { redirect } from "next/navigation";
import { ChatShell } from "@/components/chat-shell";

/**
 * Root `/` — Option A default: no Auth.js login wall.
 * Dogfood / most installs use `/embed` (Pages iframe). Set
 * DIGICHAT_REQUIRE_ROOT_AUTH=1 to require a session on `/`.
 */
export default async function Home() {
  if (!isRootAuthRequired()) {
    redirect("/embed");
  }

  const session = await auth();
  if (!session?.user) {
    // No standalone /login page — Option B (DIGICHAT_REQUIRE_ROOT_AUTH=1) has
    // no shipped deployment; fall back to the same anonymous surface Option A
    // uses rather than a dead route.
    redirect("/embed");
  }

  return (
    <ChatShell
      userId={session.user.id}
      userEmail={session.user.email}
      displayName={session.user.name}
    />
  );
}
