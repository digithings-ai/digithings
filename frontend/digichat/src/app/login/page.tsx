import { auth } from "@/auth";
import { redirect } from "next/navigation";
import { LoginForm } from "./login-form";

export default async function LoginPage() {
  const session = await auth();
  if (session?.user) {
    redirect("/");
  }

  const oidcEnabled = !!process.env.AUTH_OIDC_ISSUER?.trim();
  const devEnabled = process.env.DIGICHAT_DEV_AUTH?.trim() === "1";

  return (
    <>
      <div className="dc-grain" aria-hidden />
      <div className="relative z-10 mx-auto flex min-h-dvh w-full max-w-md flex-col items-center justify-center gap-6 px-4 py-10 sm:px-6">
        <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
          digithings · digichat
        </p>
        <LoginForm oidcEnabled={oidcEnabled} devEnabled={devEnabled} />
      </div>
    </>
  );
}
