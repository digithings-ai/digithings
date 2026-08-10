import NextAuth from "next-auth";
import type { NextAuthConfig } from "next-auth";
import Credentials from "next-auth/providers/credentials";

/** Single secret for signing/decrypting session JWT (must stay stable or users must clear cookies). */
function resolveAuthSecret(): string | undefined {
  const a = process.env.AUTH_SECRET?.trim();
  const b = process.env.NEXTAUTH_SECRET?.trim();
  return a || b || undefined;
}

function oidcProvider(): NextAuthConfig["providers"][number] | null {
  const issuer = process.env.AUTH_OIDC_ISSUER?.trim();
  const clientId = process.env.AUTH_OIDC_CLIENT_ID?.trim();
  const clientSecret = process.env.AUTH_OIDC_CLIENT_SECRET?.trim();
  if (!issuer || !clientId || !clientSecret) return null;
  return {
    id: "oidc",
    name: "Enterprise SSO",
    type: "oidc",
    issuer,
    clientId,
    clientSecret,
    authorization: { params: { scope: "openid email profile" } },
    client: { token_endpoint_auth_method: "client_secret_post" },
  };
}

function devProvider(): NextAuthConfig["providers"][number] | null {
  // Trim so values like "1\r" from CRLF .env files still enable dev login.
  if (process.env.DIGICHAT_DEV_AUTH?.trim() !== "1") return null;
  return Credentials({
    id: "dev",
    name: "Local dev",
    credentials: {
      password: { label: "Password", type: "password" },
    },
    authorize(creds) {
      // Empty DIGICHAT_DEV_PASSWORD must fall back to "dev" (?? does not treat "" as missing).
      const want = process.env.DIGICHAT_DEV_PASSWORD?.trim() || "dev";
      const got =
        typeof creds?.password === "string"
          ? creds.password.trim()
          : String(creds?.password ?? "").trim();
      if (got === want) {
        return {
          id: "dev-local",
          name: "Local Dev",
          email: "dev@digichat.local",
        };
      }
      return null;
    },
  });
}

/** Dev-only: single shared secret in DIGICHAT_LOCAL_AUTH_KEY → real JWT session (no fake bypass). */
function localBootstrapProvider(): NextAuthConfig["providers"][number] | null {
  if (process.env.NODE_ENV === "production") return null;
  const secret = process.env.DIGICHAT_LOCAL_AUTH_KEY?.trim();
  if (!secret) return null;
  return Credentials({
    id: "local-bootstrap",
    name: "Local bootstrap key",
    credentials: {
      key: { label: "Bootstrap key", type: "password" },
    },
    authorize(creds) {
      const got =
        typeof creds?.key === "string"
          ? creds.key.trim()
          : String(creds?.key ?? "").trim();
      if (got && got === secret) {
        return {
          id: "dev-local",
          name: "Local Dev",
          email: "dev@digichat.local",
        };
      }
      return null;
    },
  });
}

const oidc = oidcProvider();
const dev = devProvider();
const localBootstrap = localBootstrapProvider();
const providers = [oidc, dev, localBootstrap].filter(
  Boolean,
) as NextAuthConfig["providers"];

export const authConfig = {
  secret: resolveAuthSecret(),
  providers:
    providers.length > 0
      ? providers
      : [
          Credentials({
            id: "disabled",
            credentials: {},
            authorize: () => null,
          }),
        ],
  callbacks: {
    jwt({ token, user, account }) {
      if (account && user) {
        token.sub = user.id ?? token.sub;
        if (user.email) token.email = user.email;
        if (user.name) token.name = user.name;
      }
      return token;
    },
    session({ session, token }) {
      if (session.user) {
        session.user.id = (token.sub as string) ?? "";
      }
      return session;
    },
  },
  trustHost: true,
} satisfies NextAuthConfig;

export const { handlers, auth, signIn, signOut } = NextAuth(authConfig);
