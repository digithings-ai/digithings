"use client";
import { Terminal, type TermLine } from "@digithings/ui";

/**
 * The deployment terminal (v15, #4429).
 *
 * A scripted playback of `docker compose up` bringing the stack to life. Every
 * line is checkable against the tree: the service names and ports come from
 * `docker-compose.yml`'s un-profiled services (the set `make up` starts), and
 * the ports are the ones that file and each module's README declare. Nothing
 * here is a performance figure or an invented runtime — it is the shape of the
 * deployment, in the real names.
 *
 * The v15 pass (owner's point 7) made this a *fixed-height* box on the landing
 * page: it sits to the right of the clone command and never grows as lines
 * type in (`size="compact"` + `fill`), drops the local `http://127.0.0.1`
 * paths, and shows the whole service set rather than a slice.
 *
 * `Terminal` (packages/ui) is the primitive: it types the lines one at a time
 * at a blinking cursor and shows everything instantly under reduced motion.
 * Content is component-authored by design, which is why this file exists
 * rather than a data module — the sequence is the artefact.
 */

const LINES: TermLine[] = [
  { kind: "cmd", text: "make up" },
  { kind: "out", text: "docker compose up -d --remove-orphans" },
  { kind: "gap" },
  { kind: "out", text: "pull · build · 12 services" },
  { kind: "gap" },
  { kind: "ok", name: "valkey", text: "cache" },
  { kind: "ok", name: "digikey", text: "auth · :8005" },
  { kind: "ok", name: "digismith", text: "tracing · :8003" },
  { kind: "ok", name: "digigraph", text: "supervisor · :8000" },
  { kind: "ok", name: "digiquant", text: "quant engine · :8001" },
  { kind: "ok", name: "digisearch", text: "retrieval · :8002" },
  { kind: "ok", name: "searxng", text: "web fallback · :8888" },
  { kind: "ok", name: "litellm", text: "provider gateway · :4000" },
  { kind: "ok", name: "ollama", text: "local models · :11434" },
  { kind: "ok", name: "otel-collector", text: "otlp · :4317" },
  { kind: "ok", name: "prometheus", text: "metrics · :9090" },
  { kind: "ok", name: "grafana", text: "dashboards · :3000" },
  { kind: "gap" },
  { kind: "out", text: "up · 12 services · loopback only" },
];

export function BootTerminal({ className }: { className?: string }) {
  return (
    <div className={className}>
      <Terminal title="deploy — docker compose" lines={LINES} size="compact" fill />
    </div>
  );
}
