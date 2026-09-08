import { type DefaultSession } from "next-auth";
import { type DefaultJWT } from "next-auth/jwt";

declare module "next-auth" {
  interface User {
    /** Present when the identity provider surfaces Supabase-style claims. */
    app_metadata?: { plan_tier?: string };
  }

  interface Session {
    user: DefaultSession["user"] & {
      id: string;
      app_metadata?: { plan_tier?: string };
    };
  }
}

declare module "next-auth/jwt" {
  interface JWT extends DefaultJWT {
    plan_tier?: string;
  }
}
