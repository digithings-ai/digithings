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
    <div className="mx-auto flex min-h-dvh w-full max-w-md flex-col items-center justify-center gap-6 px-4 py-10 sm:px-6">
      <LoginForm oidcEnabled={oidcEnabled} devEnabled={devEnabled} />
    </div>
  );
}
