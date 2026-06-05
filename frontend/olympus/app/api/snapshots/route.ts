/**
 * Optional BFF for Olympus dashboard (REM-036).
 * Enable with OLYMPUS_USE_BFF=1 on the Next server; browser calls /api/snapshots
 * instead of Supabase anon when configured.
 */
import { createClient } from "@supabase/supabase-js";
import { NextResponse } from "next/server";

/** Static export bakes a build-time response; runtime BFF needs a non-export Next server. */
export const dynamic = "force-static";

function bffEnabled(): boolean {
  return process.env.OLYMPUS_USE_BFF === "1";
}

export async function GET() {
  if (!bffEnabled()) {
    return NextResponse.json(
      { error: "bff_disabled", message: "Set OLYMPUS_USE_BFF=1 to use this route" },
      { status: 404 }
    );
  }

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY?.trim();
  if (!url || !serviceKey) {
    return NextResponse.json(
      { error: "bff_misconfigured", message: "SUPABASE_SERVICE_ROLE_KEY required server-side" },
      { status: 503 }
    );
  }

  const sb = createClient(url, serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  const { data, error } = await sb
    .from("daily_snapshots")
    .select("date, run_type, snapshot, digest_markdown, baseline_date")
    .order("date", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (error) {
    return NextResponse.json({ error: "supabase_error", message: error.message }, { status: 502 });
  }

  return NextResponse.json({ snapshot: data });
}
