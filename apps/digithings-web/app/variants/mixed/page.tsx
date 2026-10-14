import type { Metadata } from "next";

import { Emblem, FeatureCell, Figure, OdometerStrip, RepoActivity, StackRow } from "@digithings/ui";
import { StandardNav } from "@/app/_variants/headers";
import { AuditCrop, BlockLabel, ByokCrop, ComposeCrop, Doc, Specimen } from "@/app/_variants/parts";
import { StackShowcase } from "@/app/_variants/stack-showcase";
import { CLAIM, COUNTS, LEDE, METRICS, MODULE_ROWS } from "@/app/_variants/content";
import { DtFooter } from "@/components/DtFooter";
import { CONTRIBUTING_URL, REPO_CLONE, REPO_LIVE, REPO_URL, repoActivity } from "@/lib/repoActivity";

// V8 · The mixed composition — Registry's card-first narrow page, with
// Specimen's frame rhythm and "what it buys you". The stack leads and its focus
// travels as you scroll; every other block is a labelled frame. Exploration.

export const metadata: Metadata = {
  title: "V8 · Mixed — variant",
  robots: { index: false, follow: false },
};

/** The three roadmap modules, kept out of the showcase so it focuses on what ships. */
const ROADMAP = MODULE_ROWS.filter((m) => m.tier === "roadmap");

export default function VariantMixed() {
  return (
    <>
      <StandardNav />

      <main id="main" tabIndex={-1} className="pt-[var(--dq-nav-h)] pb-[var(--page-step)]">
        <Doc className="grid gap-[1rem] pt-[var(--page-step)]">
          {/* The claim, in the reference's frame rhythm. */}
          <Specimen label="digithings · open core">
            <h1 className="m-0 max-w-[20ch] font-mono text-[length:var(--type-hero)] font-medium leading-[1.14] tracking-[-0.02em] text-ink">
              {CLAIM}
            </h1>
            <p className="mt-[1.1rem] mb-0 max-w-[var(--measure-prose)] text-[length:var(--type-body)] leading-[var(--leading-prose)] text-ink-soft">
              {LEDE}
            </p>
          </Specimen>

          {/* The stack: the map, with a travelling focus. */}
          <div className="border border-hair bg-surface p-[1.25rem]">
            <div className="flex flex-wrap items-baseline justify-between gap-[0.8rem]">
              <BlockLabel>the stack · {COUNTS.shipping} modules shipping</BlockLabel>
              {/* The hint is desktop-only: below 900px (and under reduced motion)
                  the showcase degrades to the plain grid with details inline, so
                  there is no focus to move. */}
              <span className="hidden font-mono text-[0.6rem] uppercase tracking-[var(--tracking-meta)] text-ink-mute min-[900px]:inline">
                scroll to move focus
              </span>
            </div>
            <p className="mt-[0.7rem] mb-0 max-w-[68ch] text-[0.92rem] leading-[1.7] text-ink-soft">
              Weight follows tier: the supervisor anchors the grid, the flagship runs wide, the rest
              take a cell each. On a wide screen the card beside it follows you down.
            </p>
            <div className="mt-[1.4rem]">
              <StackShowcase />
            </div>
          </div>

          {/* What it buys you — the part of Specimen that worked, tightened. */}
          <Specimen label="what it buys you">
            <div className="grid gap-[1.4rem]">
              <FeatureCell
                eyebrow="one file"
                outcome="Self-hosted, loopback by default"
                mechanism={`One docker-compose.yml brings up ${COUNTS.compose} services, every one bound to 127.0.0.1 until you say otherwise.`}
                href="/docs"
                linkLabel="Read the deploy guide"
                linkAriaLabel="Read the digithings deploy guide"
              >
                <ComposeCrop />
              </FeatureCell>

              <FeatureCell
                eyebrow="bring your own key"
                outcome="Forwarded per request, never stored"
                mechanism={`Your provider key lives in one tab's memory. The site persists two preference strings and nothing else — ${COUNTS.keysStored} keys stored, ever.`}
                href="/legal/privacy"
                linkLabel="Read the privacy notice"
                linkAriaLabel="Read the digithings privacy notice"
              >
                <ByokCrop />
              </FeatureCell>

              <FeatureCell
                eyebrow="audit on by default"
                outcome="Every hop lands on your disk"
                mechanism="A correlation id rides every service call, and workflow events append to a JSONL trail you own — redacted by key name on the way in."
                href="/security"
                linkLabel="Read the security posture"
                linkAriaLabel="Read the digithings security posture"
              >
                <AuditCrop />
              </FeatureCell>
            </div>
          </Specimen>

          <Specimen label={`fig 1 · counted ${COUNTS.countedAt}`}>
            <Figure n={1} caption="Single-sourced in lib/siteCounts.ts, each figure with the command that produced it.">
              <OdometerStrip stats={METRICS} />
            </Figure>
          </Specimen>

          {/* One shared chrome dependency list, rather than eleven repeated ones. */}
          <Specimen label="assembled from parts you can name">
            <p className="m-0 max-w-[68ch] text-[0.92rem] leading-[1.7] text-ink-soft">
              Every module composes with open-source libraries you can version and swap — no forks,
              no reimplementations of a database, a scheduler, or a model runtime.
            </p>
            <div className="mt-[1.3rem]">
              <StackRow
                items={[
                  { name: "LangGraph", icon: "langgraph" },
                  { name: "LiteLLM", icon: null, mono: "LL" },
                  { name: "NautilusTrader", icon: null, mono: "NT" },
                  { name: "Optuna", icon: "optuna" },
                  { name: "Polars", icon: "polars" },
                  { name: "Pydantic", icon: "pydantic" },
                  { name: "FastAPI", icon: "fastapi" },
                  { name: "Postgres", icon: "postgresql" },
                  { name: "Redis", icon: "redis" },
                  { name: "OpenTelemetry", icon: "opentelemetry" },
                  { name: "MCP", icon: "modelcontextprotocol" },
                  { name: "Docker", icon: "docker" },
                ]}
              />
            </div>
          </Specimen>

          <Specimen label="fig 2 · the repository">
            <RepoActivity
              variant="detailed"
              snapshot={repoActivity}
              repoUrl={REPO_URL}
              live={REPO_LIVE}
              cloneCommand={REPO_CLONE}
              contributingUrl={CONTRIBUTING_URL}
            />
          </Specimen>

          {/* The roadmap pair, out of the showcase and stated plainly. */}
          <Specimen label="roadmap · not shipped">
            <div className="grid gap-[1rem] min-[700px]:grid-cols-2">
              {ROADMAP.map((m) => (
                <div key={m.id} className="border border-hair p-[1rem]">
                  <div className="flex items-center gap-[0.6rem]">
                    <Emblem id={m.emblem} size={18} />
                    <span className="font-mono text-[0.95rem] text-ink">{m.name}</span>
                  </div>
                  <p className="mt-[0.5rem] mb-0 text-[0.85rem] leading-[1.65] text-ink-soft">{m.role}</p>
                </div>
              ))}
            </div>
          </Specimen>
        </Doc>
      </main>

      <DtFooter />
    </>
  );
}
