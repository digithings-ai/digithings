"use client";

import type { DigigraphTracePayload } from "@/lib/stream-digigraph-trace";
import { BookOpen, Braces, GitBranch, Search } from "lucide-react";

function TraceIcon({ t }: { t: string }) {
  if (t === "rag_sources") return <Search className="h-3.5 w-3.5 shrink-0 opacity-80" />;
  if (t === "code_block") return <Braces className="h-3.5 w-3.5 shrink-0 opacity-80" />;
  if (t === "graph_update" || t === "graph_step")
    return <GitBranch className="h-3.5 w-3.5 shrink-0 opacity-80" />;
  return <BookOpen className="h-3.5 w-3.5 shrink-0 opacity-80" />;
}

export function DigigraphTraceCard({ trace }: { trace: DigigraphTracePayload }) {
  const t = trace.type;
  const payload = trace.payload ?? {};
  const svc = trace.service?.trim();
  return (
    <div className="rounded-md border border-border/50 bg-term-bg px-3 py-2 text-xs">
      <div className="mb-1 flex items-center gap-2 font-medium text-muted-foreground">
        <TraceIcon t={t} />
        <span className="uppercase tracking-wide">{t.replace(/_/g, " ")}</span>
        {svc ? (
          <span className="rounded bg-muted/50 px-1.5 py-0.5 font-mono text-[10px]">{svc}</span>
        ) : null}
        {trace.workflow_id ? (
          <span className="ml-auto truncate font-mono text-[10px] opacity-70">
            {trace.workflow_id.slice(0, 8)}…
          </span>
        ) : null}
      </div>
      {t === "rag_sources" && Array.isArray(payload.sources) ? (
        <ul className="mt-2 space-y-2">
          {(payload.sources as Array<Record<string, unknown>>).slice(0, 8).map((s, i) => (
            <li key={i} className="rounded border border-border/40 bg-background/40 px-2 py-1.5">
              <div className="text-[11px] text-muted-foreground">
                {String(s.doc_id ?? "doc")}{" "}
                {s.score != null ? `· score ${String(s.score)}` : null}
              </div>
              {s.snippet ? (
                <div className="mt-1 line-clamp-3 text-[11px] leading-snug text-foreground/90">
                  {String(s.snippet)}
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      ) : t === "code_block" && typeof payload.content === "string" ? (
        <pre className="mt-1 max-h-48 overflow-auto rounded bg-term-fill p-2 font-mono text-[11px] leading-relaxed text-term-ink">
          {payload.content as string}
        </pre>
      ) : (
        <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap font-mono text-[11px] text-muted-foreground">
          {JSON.stringify(payload, null, 2)}
        </pre>
      )}
    </div>
  );
}
