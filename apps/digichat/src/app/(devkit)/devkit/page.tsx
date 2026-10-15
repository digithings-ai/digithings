import { notFound } from "next/navigation";
import { DevkitClient } from "./devkit-client";

export const dynamic = "force-dynamic";

/** Local config workbench. Dev-only — not a production surface. */
export default function DevkitPage() {
  if (process.env.NODE_ENV === "production") notFound();
  return <DevkitClient />;
}
