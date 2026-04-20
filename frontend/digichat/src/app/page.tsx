import { auth } from "@/auth";
import { redirect } from "next/navigation";
import { ChatShell } from "@/components/chat-shell";

export default async function Home() {
  const session = await auth();
  if (!session?.user) {
    redirect("/login");
  }

  return (
    <ChatShell
      userId={session.user.id}
      userEmail={session.user.email}
      displayName={session.user.name}
    />
  );
}
