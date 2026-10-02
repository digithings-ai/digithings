"use client";

import { useRef, useState } from "react";
import type { StageSnapshot } from "@/lib/run-snapshot";
import { officialGet } from "@/lib/official-api";
import { Button } from "@digithings/ui/ui";
import { STAGE_COPY } from "./stage-copy";
import { loadStepOutput, type StepDocumentView, type StepOutputRead } from "./step-output";

const STEP_BUTTON =
  "h-auto w-full justify-start gap-2 whitespace-normal border-0 border-t border-hair bg-transparent px-0 py-2.5 text-start font-mono text-[0.875rem] font-normal leading-[1.45] text-ink-soft hover:bg-transparent";

function stepDomId(index: number, step: string): string {
  const slug = step
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  return `stage-${index}-step-${slug}`;
}

/** What a step click loaded. An em dash stands in for a missing field. */
export function StepOutputPanel({ read }: { read: StepOutputRead }) {
  return (
    <div role="region" aria-label="Step output" data-step-output="" className="flex flex-col gap-3 border-t border-hair pt-4 font-sans">
      <p className="m-0 text-[0.9375rem] leading-[1.6] text-ink-soft">{read.reason}</p>
      {read.documents.length === 0 ? (
        <p className="m-0 font-mono text-[1.5rem] leading-none text-ink">—</p>
      ) : (
        read.documents.map((doc) => <StepDocument key={doc.documentKey} doc={doc} />)
      )}
    </div>
  );
}

function StepDocument({ doc }: { doc: StepDocumentView }) {
  return (
    <article className="flex flex-col gap-2 border-t border-hair pt-3">
      <h4 className="m-0 text-[1rem] font-medium leading-snug text-ink">{doc.title ?? doc.documentKey}</h4>
      <p className="m-0 font-mono text-[0.75rem] text-ink-mute">{doc.documentKey}</p>
      {doc.fields.length === 0 ? (
        <p className="m-0 font-mono text-[1.5rem] leading-none text-ink">—</p>
      ) : (
        doc.fields.map((field) => (
          <div key={field.key} className="flex flex-col gap-1">
            <p className="m-0 font-mono text-[0.72rem] text-ink-mute">{field.key}</p>
            <pre className="m-0 max-h-[24rem] overflow-y-auto whitespace-pre-wrap font-sans text-[0.9375rem] leading-[1.6] text-ink-soft">
              {field.text}
            </pre>
          </div>
        ))
      )}
    </article>
  );
}

function MissingDetail({ children }: { children: string }) {
  return (
    <div className="flex flex-col gap-2">
      <p className="m-0 font-mono text-[1.5rem] leading-none text-ink">—</p>
      <p className="m-0 text-[0.9375rem] leading-[1.55] text-ink-soft">{children}</p>
    </div>
  );
}

/** One stage on the deck: full copy, every sub-step, and the recorded run's detail. */
export function StageCard({
  index,
  total,
  name,
  recorded,
  hasRun,
  runDate,
}: {
  index: number;
  total: number;
  name: keyof typeof STAGE_COPY;
  recorded: StageSnapshot | undefined;
  hasRun: boolean;
  runDate: string | null;
}) {
  const copy = STAGE_COPY[name];
  const n = String(index + 1).padStart(2, "0");
  const ticket = useRef(0);
  const [openStep, setOpenStep] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [output, setOutput] = useState<StepOutputRead | null>(null);

  const onStep = (step: string) => {
    if (openStep === step && !pending) {
      setOpenStep(null);
      setOutput(null);
      return;
    }
    const id = ticket.current + 1;
    ticket.current = id;
    setOpenStep(step);
    setPending(true);
    setOutput(null);
    void loadStepOutput(officialGet, name, step, runDate).then((read) => {
      if (ticket.current !== id) return;
      setOutput(read);
      setPending(false);
    });
  };

  return (
    <article
      aria-label={`Stage ${index + 1} of ${total}: ${name}`}
      className="flex h-full min-h-[28rem] w-full min-w-0 flex-col border border-hair bg-surface"
    >
      <div className="flex items-baseline justify-between border-b border-hair px-5 py-3 font-mono text-[0.75rem] text-ink-mute">
        <span>
          {n}/{String(total).padStart(2, "0")}
        </span>
        <span>{hasRun ? (recorded?.status === "recorded" ? "recorded" : "not recorded") : "no recorded run"}</span>
      </div>
      <div className="flex flex-1 flex-col gap-4 p-5">
        <div className="flex flex-col gap-3">
          <h3 className="m-0 font-display text-[1.45rem] font-medium leading-[1.2] tracking-[-0.02em] text-ink">{name}</h3>
          <p className="m-0 text-[0.975rem] leading-[1.65] text-ink-soft">{copy.does}</p>
          <div className="flex flex-col">
            {copy.steps.map((step) => {
              const open = openStep === step;
              return (
                <Button
                  key={step}
                  type="button"
                  variant="ghost"
                  size="sm"
                  aria-expanded={open}
                  aria-controls={open ? stepDomId(index, step) : undefined}
                  onClick={() => onStep(step)}
                  className={STEP_BUTTON}
                >
                  <span aria-hidden="true" className="text-ink-mute">
                    ▸
                  </span>
                  {step}
                </Button>
              );
            })}
          </div>
        </div>
        <div className="mt-auto flex flex-col gap-3 border-t border-hair pt-4 font-mono text-[0.8125rem] text-ink-mute">
          {recorded ? (
            <>
              <p className="m-0 text-[0.875rem] leading-[1.5] text-ink-soft">
                {recorded.documentCount} {recorded.documentCount === 1 ? "document" : "documents"} in the recorded run
              </p>
              {recorded.titles && recorded.titles.length > 0 ? (
                <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
                  {recorded.titles.map((title) => (
                    <li key={title} className="text-[0.875rem] leading-[1.45] text-ink-soft">
                      {title}
                    </li>
                  ))}
                </ul>
              ) : (
                <MissingDetail>No titles were recorded for this stage.</MissingDetail>
              )}
            </>
          ) : (
            <MissingDetail>No run detail was recorded in this build.</MissingDetail>
          )}
          {openStep ? (
            <div id={stepDomId(index, openStep)}>
              {pending || !output ? (
                <p className="m-0 text-[0.9375rem] leading-[1.55] text-ink-soft">Reading this step from the official API.</p>
              ) : (
                <StepOutputPanel read={output} />
              )}
            </div>
          ) : null}
        </div>
      </div>
    </article>
  );
}

/** The dashed last card: execution is not built. */
export function ExecutionCard({ index, total, status }: { index: number; total: number; status: string }) {
  const n = String(index + 1).padStart(2, "0");
  return (
    <article
      aria-label={`Stage ${index + 1} of ${total}: Execution, ${status}`}
      className="flex h-full min-h-[28rem] w-full min-w-0 flex-col border border-dashed border-hair bg-transparent"
    >
      <div className="flex items-baseline justify-between border-b border-dashed border-hair px-5 py-3 font-mono text-[0.75rem] text-ink-mute">
        <span>
          {n}/{String(total).padStart(2, "0")}
        </span>
        <span>{status}</span>
      </div>
      <div className="flex flex-1 flex-col gap-4 p-5">
        <h3 className="m-0 font-display text-[1.45rem] font-medium leading-[1.2] tracking-[-0.02em] text-ink-soft">Execution</h3>
        <p className="m-0 text-[0.975rem] leading-[1.65] text-ink-mute">
          Not built. The six stages end in a recorded decision; nothing places an order.
        </p>
      </div>
    </article>
  );
}
