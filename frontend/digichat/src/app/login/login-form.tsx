"use client";

import { signIn } from "next-auth/react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { p } from "@/lib/base-path";

export function LoginForm({
  oidcEnabled,
  devEnabled,
}: {
  oidcEnabled: boolean;
  devEnabled: boolean;
}) {
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);

  return (
    <Card className="w-full max-w-md border-border/60 bg-card/60 p-8">
      <p className="mb-1 font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
        {"> "}auth
      </p>
      <h1 className="mb-2 text-xl font-semibold tracking-tight">Sign in to DigiChat.</h1>
      <p className="mb-6 font-mono text-xs text-muted-foreground">
        organization SSO or local dev credentials.
      </p>
      <div className="flex flex-col gap-3">
        {oidcEnabled ? (
          <Button type="button" className="w-full" onClick={() => signIn("oidc", { callbackUrl: p("/") })}>
            Continue with SSO
          </Button>
        ) : (
          <p className="text-sm text-amber-200/90">
            OIDC is not configured (set AUTH_OIDC_ISSUER, AUTH_OIDC_CLIENT_ID,
            AUTH_OIDC_CLIENT_SECRET).
          </p>
        )}
        {!oidcEnabled && !devEnabled ? (
          <div className="rounded-md border border-border/60 bg-muted/25 p-3 text-xs leading-relaxed text-muted-foreground">
            <p className="font-medium text-foreground">Local sign-in</p>
            <p className="mt-1">
              Add to <code className="rounded bg-background/80 px-1">digichat/.env.local</code>:
            </p>
            <pre className="mt-2 overflow-x-auto rounded border border-border/50 bg-background/50 p-2 font-mono text-[11px] text-foreground">
              DIGICHAT_DEV_AUTH=1{"\n"}
              DIGICHAT_DEV_PASSWORD=dev{"\n"}
              AUTH_SECRET=dev-secret-change-me{"\n"}
              AUTH_URL=http://127.0.0.1:3000
            </pre>
            <p className="mt-2">
              Restart <code className="rounded bg-background/80 px-1">npm run dev</code> and reload —
              a <strong className="text-foreground">Dev sign-in</strong> section will appear; default
              password is <code className="rounded bg-background/80 px-1">dev</code> unless you set{" "}
              <code className="rounded bg-background/80 px-1">DIGICHAT_DEV_PASSWORD</code>.
            </p>
          </div>
        ) : null}
        {devEnabled ? (
          <form
            className="space-y-2 border-t border-border/40 pt-4"
            onSubmit={async (e) => {
              e.preventDefault();
              setErr(null);
              const res = await signIn("dev", {
                password,
                redirect: false,
                callbackUrl: p("/"),
              });
              if (res?.error) setErr("Invalid dev password.");
              else if (res?.ok) window.location.href = p("/");
            }}
          >
            <label className="text-xs font-medium text-muted-foreground">
              Dev password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
              autoComplete="off"
            />
            <Button type="submit" variant="secondary" className="w-full">
              Dev sign-in
            </Button>
            {err ? <p className="text-sm text-destructive">{err}</p> : null}
          </form>
        ) : null}
      </div>
    </Card>
  );
}
