"use client";
import { Terminal, type TermLine } from "@digithings/ui";

/**
 * The deployment terminal (v15, #4429; simplified in round 2).
 *
 * A scripted playback of `make up` bringing the digi modules online. Every line
 * is checkable against the tree: `make up` really is `docker compose up -d`
 * (Makefile:9-10), and `digi-digikey` / `digi-digismith` / `digi-digigraph` /
 * `digi-digiquant` / `digi-digisearch` are the compose file's real container
 * names for the five digi services that a bare `docker compose up -d` starts.
 *
 * The owner's direction for this round: "remove all the non-digi modules remove
 * their localhost path i just keep it simple… fix the terminal height and fill
 * it with a few digi". So the third-party sidecars (valkey, ollama, searxng,
 * litellm, otel-collector, prometheus, grafana) and every port are gone, and the
 * list is the digi modules alone.
 *
 * There is deliberately **no `[+] Running N/N` line**, even though real compose
 * prints one. The count it would print is 11 — five digi services plus six
 * sidecars — and showing "5/5" above a five-line list would assert that `make up`
 * starts five containers, which is false. The ✓ list is the modules coming up,
 * not a claim about the size of the stack, so the terminal simply does not state
 * a total. (The closing line says `loopback only`, which is the real default.)
 *
 * `Terminal` (packages/ui) types the lines one at a time at a blinking cursor
 * and shows everything instantly under reduced motion. The height is fixed by
 * the caller — see the `Boot` band — so the box never grows as it types.
 * Content is component-authored by design, which is why this file exists rather
 * than a data module: the sequence is the artefact.
 */

const LINES: TermLine[] = [
  { kind: "cmd", text: "make up" },
  { kind: "out", text: "docker compose up -d" },
  { kind: "gap" },
  { kind: "ok", name: "digi-digikey", text: "started" },
  { kind: "ok", name: "digi-digismith", text: "started" },
  { kind: "ok", name: "digi-digigraph", text: "started" },
  { kind: "ok", name: "digi-digiquant", text: "started" },
  { kind: "ok", name: "digi-digisearch", text: "started" },
  { kind: "gap" },
  { kind: "out", text: "stack ready · loopback only" },
];

export function BootTerminal({ className }: { className?: string }) {
  return (
    <div className={className}>
      <Terminal title="deploy — docker compose" lines={LINES} size="compact" fill />
    </div>
  );
}
