import { notFound } from "next/navigation";
import { BaselineClient } from "./baseline-client";

export const dynamic = "force-dynamic";

/** Localhost stock assistant-ui. Proxies production digithings.ai chat. Not a production surface. */
export default function BaselinePage() {
  if (process.env.NODE_ENV === "production") notFound();
  return <BaselineClient />;
}
