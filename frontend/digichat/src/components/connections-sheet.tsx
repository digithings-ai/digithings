"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, Plug, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import type { EcosystemEndpoints } from "@/lib/ecosystem";

type HealthChecks = Record<string, string>;

export function ConnectionsSheet() {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [defaults, setDefaults] = useState<EcosystemEndpoints | null>(null);
  const [form, setForm] = useState<EcosystemEndpoints | null>(null);
  const [hasCustom, setHasCustom] = useState(false);
  const [health, setHealth] = useState<HealthChecks | null>(null);
  const [persistence, setPersistence] = useState<{ serverDatabaseConfigured: boolean } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const r = await fetch("/api/ecosystem/config", { credentials: "include" });
      if (!r.ok) {
        setErr(`Config ${r.status}: ${await r.text()}`);
        return;
      }
      const data = (await r.json()) as {
        effective: EcosystemEndpoints;
        defaults: EcosystemEndpoints;
        hasCustomEndpoints: boolean;
        persistence?: { serverDatabaseConfigured: boolean };
      };
      setDefaults(data.defaults);
      setForm(data.effective);
      setHasCustom(data.hasCustomEndpoints);
      setPersistence(data.persistence ?? null);
      const h = await fetch("/api/health", { credentials: "include" });
      if (h.ok) {
        const hj = (await h.json()) as { checks?: HealthChecks };
        setHealth(hj.checks ?? null);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Load failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  async function onSave(e: React.FormEvent) {
    e.preventDefault();
    if (!form) return;
    setSaving(true);
    setErr(null);
    try {
      const r = await fetch("/api/ecosystem/config", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (!r.ok) {
        setErr(await r.text());
        return;
      }
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function onReset() {
    setSaving(true);
    setErr(null);
    try {
      const r = await fetch("/api/ecosystem/config", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reset: true }),
      });
      if (!r.ok) {
        setErr(await r.text());
        return;
      }
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Reset failed");
    } finally {
      setSaving(false);
    }
  }

  function resetFormToDefaults() {
    if (defaults) setForm({ ...defaults });
  }

  return (
    <>
      <Button type="button" variant="outline" size="sm" onClick={() => setOpen(true)}>
        <Plug className="mr-2 h-4 w-4" />
        Ecosystem
      </Button>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-lg">
        <SheetHeader>
          <SheetTitle>DigiThings connections</SheetTitle>
          <SheetDescription>
            Base URLs for the Python stack (DigiGraph, DigiQuant, DigiSmith, DigiSearch). Host dev defaults:
            <code className="mx-1 text-[11px]">127.0.0.1:8000–8003,8002</code>. Overrides are stored in an
            httpOnly cookie for this browser session.
          </SheetDescription>
        </SheetHeader>

        {err ? (
          <p className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm">{err}</p>
        ) : null}

        {loading || !form ? (
          <div className="mt-8 flex justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <form onSubmit={onSave} className="mt-6 space-y-5">
            {health ? (
              <div className="flex flex-wrap gap-2 text-xs">
                {(
                  [
                    "digraph",
                    "digiquant",
                    "digismith",
                    "digisearch",
                    "database",
                  ] as const
                ).map((k) => (
                  <Badge
                    key={k}
                    variant={health[k] === "ok" ? "default" : "secondary"}
                    className={
                      health[k] === "ok" ? "bg-emerald-600/90 hover:bg-emerald-600" : "bg-amber-900/40"
                    }
                  >
                    {k}: {health[k] ?? "—"}
                  </Badge>
                ))}
              </div>
            ) : null}

            <div className="space-y-2">
              <Label htmlFor="dg">DigiGraph base URL</Label>
              <Input
                id="dg"
                value={form.digigraphUrl}
                onChange={(e) => setForm({ ...form, digigraphUrl: e.target.value })}
                placeholder="http://127.0.0.1:8000"
                autoComplete="off"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="dq">DigiQuant base URL</Label>
              <Input
                id="dq"
                value={form.digiquantUrl}
                onChange={(e) => setForm({ ...form, digiquantUrl: e.target.value })}
                placeholder="http://127.0.0.1:8001"
                autoComplete="off"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="ds">DigiSmith base URL</Label>
              <Input
                id="ds"
                value={form.digismithUrl}
                onChange={(e) => setForm({ ...form, digismithUrl: e.target.value })}
                placeholder="http://127.0.0.1:8003"
                autoComplete="off"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="dsearch">DigiSearch base URL</Label>
              <Input
                id="dsearch"
                value={form.digisearchUrl ?? ""}
                onChange={(e) =>
                  setForm({
                    ...form,
                    digisearchUrl: e.target.value.trim() || undefined,
                  })
                }
                placeholder="http://127.0.0.1:8002"
                autoComplete="off"
              />
              <p className="text-xs text-muted-foreground">
                RAG / orchestrator hub uses this for health and (via DigiGraph) <code className="text-[11px]">DIGISEARCH_URL</code>{" "}
                must match on the graph side. Docker Compose uses service names; native stack uses loopback.
              </p>
            </div>

            {persistence && !persistence.serverDatabaseConfigured ? (
              <div className="rounded-md border border-amber-900/40 bg-amber-950/20 p-3 text-xs text-muted-foreground">
                <p className="font-medium text-foreground">Postgres not configured</p>
                <p className="mt-1">
                  <strong>database: skipped</strong> means <code className="text-[11px]">DIGICHAT_DATABASE_URL</code> is unset
                  — conversations stay in the browser only. For server-side history, tenants, and API keys, run Postgres locally
                  (<code className="text-[11px]">make up-digichat-db</code> from the repo root) and set{" "}
                  <code className="text-[11px]">
                    postgresql://digichat:digichat@127.0.0.1:5433/digichat
                  </code>{" "}
                  in <code className="text-[11px]">digichat/.env.local</code>, then <code className="text-[11px]">npm run db:migrate</code>.
                </p>
              </div>
            ) : persistence?.serverDatabaseConfigured ? (
              <p className="text-xs text-muted-foreground">
                Server persistence: Postgres is configured (<code className="text-[11px]">DIGICHAT_DATABASE_URL</code>). The{" "}
                <strong>database</strong> badge reflects a live <code className="text-[11px]">SELECT 1</code>.
              </p>
            ) : null}

            <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
              <Button type="submit" disabled={saving}>
                Save &amp; apply
              </Button>
              <Button type="button" variant="secondary" onClick={() => void load()} disabled={saving}>
                <RefreshCw className="mr-2 h-4 w-4" />
                Refresh status
              </Button>
              <Button type="button" variant="outline" onClick={resetFormToDefaults} disabled={saving}>
                Copy defaults into form
              </Button>
              <Button
                type="button"
                variant="ghost"
                onClick={() => void onReset()}
                disabled={saving || !hasCustom}
              >
                Clear overrides (use server env)
              </Button>
            </div>
            {hasCustom ? (
              <p className="text-xs text-muted-foreground">Custom endpoints are active (cookie).</p>
            ) : (
              <p className="text-xs text-muted-foreground">Using server environment defaults.</p>
            )}
          </form>
        )}
      </SheetContent>
      </Sheet>
    </>
  );
}
