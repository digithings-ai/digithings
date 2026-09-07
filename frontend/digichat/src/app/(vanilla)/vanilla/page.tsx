import { notFound } from "next/navigation";
import { VanillaClient } from "./vanilla-client";

export const dynamic = "force-dynamic";

/** Localhost stock assistant-ui. Proxies production digithings.ai chat. Not a production surface. */
export default function VanillaPage() {
  if (process.env.NODE_ENV === "production") notFound();
  return <VanillaClient />;
}
