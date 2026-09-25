/**
 * Navigable pipeline card for expanded mosaic tiles (#4429, restart).
 *
 * One module's public tool surface as a kit `Pipeline`: every node is a
 * real tool or tool group, selecting it shows what it does and what it
 * takes. The card adds what `Pipeline` itself does not own: the header
 * copy, the per-node honesty foot (paper-only, docs pointers), the usage
 * snippet, and the proof/connects rows. All copy arrives via props —
 * preformatted display strings, nothing formatted here.
 *
 * Only digiquant has data so far (`pipelineCards`); the renderer is
 * generic so the other ten specs drop in as data.
 */
"use client";

import { useState } from "react";

import { Pipeline } from "../effects-chrome";
import { cn } from "../../lib/utils";
import type { PipelineCardData } from "../../data/pipelineCards";

function SnippetBlock({ label, code }: { label: string; code: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    const done = () => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    };
    try {
      const clip = typeof navigator === "undefined" ? undefined : navigator.clipboard;
      if (clip?.writeText) {
        void clip.writeText(code).then(done, () => undefined);
        return;
      }
    } catch {
      /* fall through — no clipboard, no claim */
    }
  };
  return (
    <div className="m-pipe-code">
      <div className="m-pipe-code-head">
        <span>{label}</span>
        <button type="button" onClick={copy} aria-label={copied ? "Copied" : `Copy: ${label}`}>
          {copied ? "copied" : "copy"}
        </button>
      </div>
      <pre>{code}</pre>
    </div>
  );
}

export function PipelineCard({ card, className }: { card: PipelineCardData; className?: string }) {
  const [selId, setSelId] = useState<string | undefined>(undefined);
  const foot = card.foot[selId ?? card.defaultSelectedId];
  return (
    <div className={cn("m-pipe", card.motifClass, className)}>
      <p className="m-pipe-kicker">{card.kicker}</p>
      <p className="m-pipe-title">{card.title}</p>
      <p className="m-pipe-lede">{card.lede}</p>
      <div className="m-pipe-badges" aria-label="Module facts">
        {card.badges.map((b) => (
          <span key={b}>{b}</span>
        ))}
      </div>
      {card.sub ? <p className="m-pipe-sub">{card.sub}</p> : null}
      {card.notice ? <p className="m-pipe-notice">{card.notice}</p> : null}
      <Pipeline
        columns={card.columns}
        summary={card.summary}
        defaultSelectedId={card.defaultSelectedId}
        onSelect={(n) => setSelId(n.id)}
      />
      {foot ? <p className="m-pipe-foot">{foot}</p> : null}
      <div className="m-pipe-snippet">
        {card.snippet.map((s) => (
          <SnippetBlock key={s.label} label={s.label} code={s.code} />
        ))}
        <p className="m-pipe-caption">{card.snippetCaption}</p>
      </div>
      <ul className="m-pipe-proof" aria-label="Proof">
        {card.proof.map((p) => (
          <li key={p}>{p}</li>
        ))}
      </ul>
      <p className="m-pipe-connects">{card.connects.join(" · ")}</p>
    </div>
  );
}
