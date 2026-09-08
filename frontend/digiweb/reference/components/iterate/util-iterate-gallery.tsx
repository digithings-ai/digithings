"use client";

import { useMemo, useSyncExternalStore } from "react";
import {
  UTIL_AXES,
  clearUtilPrefs,
  formatUtilPrefsMarkdown,
  getUtilPrefsServerSnapshot,
  getUtilPrefsSnapshot,
  setUtilPref,
  subscribeUtilPrefs,
  type UtilVariant,
} from "@/components/iterate/util-prefs-store";

/**
 * Utilitarian terminal iterate gallery — side-by-side treatments for every
 * foundational digiweb axis, inspired by herdr / agentmail / omarchy / our
 * Instrument Panel. Click a card to record a preference; the sticky ledger
 * exports markdown for design/BLEND.md. Gallery-only (`uv-` CSS); not production.
 */
export function UtilIterateGallery() {
  const prefs = useSyncExternalStore(
    subscribeUtilPrefs,
    getUtilPrefsSnapshot,
    getUtilPrefsServerSnapshot,
  );

  const picked = useMemo(
    () => UTIL_AXES.filter((a) => prefs[a.id]).length,
    [prefs],
  );

  const exportMd = formatUtilPrefsMarkdown(prefs);

  return (
    <div className="uv-page">
      <aside className="uv-ledger" aria-label="Preference ledger">
        <p className="uv-ledger-kicker">{"// ledger"}</p>
        <h2 className="uv-ledger-title">
          {picked}/{UTIL_AXES.length} axes picked
        </h2>
        <ul className="uv-ledger-list">
          {UTIL_AXES.map((axis) => {
            const v = axis.variants.find((x) => x.id === prefs[axis.id]);
            return (
              <li key={axis.id}>
                <span>{axis.label}</span>
                <strong>{v ? v.label : "—"}</strong>
              </li>
            );
          })}
        </ul>
        <div className="uv-ledger-actions">
          <button
            type="button"
            className="uv-btn uv-btn-ink"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(exportMd);
              } catch {
                /* ignore */
              }
            }}
          >
            Copy markdown
          </button>
          <button type="button" className="uv-btn uv-btn-ghost" onClick={() => clearUtilPrefs()}>
            Clear
          </button>
        </div>
        <p className="uv-ledger-hint">
          Paste into <code>frontend/digiweb/design/BLEND.md</code> when a round feels right.
        </p>
      </aside>

      <div className="uv-axes">
        {UTIL_AXES.map((axis) => (
          <section key={axis.id} className="uv-axis" id={axis.id}>
            <p className="uv-kicker">{`// ${axis.id}`}</p>
            <h2 className="uv-axis-title">{axis.label}</h2>
            <p className="uv-axis-prompt">{axis.prompt}</p>
            <div
              className="uv-grid"
              role="radiogroup"
              aria-label={axis.label}
            >
              {axis.variants.map((variant) => (
                <VariantCard
                  key={variant.id}
                  axisId={axis.id}
                  variant={variant}
                  selected={prefs[axis.id] === variant.id}
                  onSelect={() => setUtilPref(axis.id, variant.id)}
                />
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}

function VariantCard({
  axisId,
  variant,
  selected,
  onSelect,
}: {
  axisId: string;
  variant: UtilVariant;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      className={`uv-card${selected ? " is-on" : ""}`}
      onClick={onSelect}
    >
      <div className={`uv-preview uv-preview--${axisId} uv-preview--${axisId}--${variant.id}`}>
        <Preview axisId={axisId} variantId={variant.id} />
      </div>
      <div className="uv-card-meta">
        <span className="uv-card-label">{variant.label}</span>
        <span className="uv-card-src">{variant.inspiredBy}</span>
        <span className="uv-card-note">{variant.note}</span>
      </div>
    </button>
  );
}

function Preview({ axisId, variantId }: { axisId: string; variantId: string }) {
  switch (axisId) {
    case "radius-controls":
      return (
        <div className="uv-demo-row">
          <span className={`uv-chip uv-r-${variantId}`}>Run</span>
          <span className={`uv-chip uv-r-${variantId} is-ghost`}>Docs</span>
        </div>
      );
    case "radius-cards":
      return <div className={`uv-panel uv-card-r-${variantId}`}>Panel</div>;
    case "type-voice":
      return (
        <div className={`uv-type uv-type--${variantId}`}>
          <p className="uv-type-display">Run them anywhere.</p>
          <p className="uv-type-body">Body copy stays calm and readable.</p>
          <p className="uv-type-mono">{"// INSTALL · 12px"}</p>
        </div>
      );
    case "primary-cta":
      return (
        <div className="uv-demo-row">
          <span className={`uv-cta uv-cta--${variantId}`}>Start</span>
          <span className="uv-chip uv-r-sharp is-ghost">Docs</span>
        </div>
      );
    case "nav-chrome":
      return (
        <nav className={`uv-nav uv-nav--${variantId}`} aria-hidden="true">
          <span className="uv-nav-brand">digi</span>
          <span>Docs</span>
          <span>Pricing</span>
          <span className="uv-nav-cta">Install</span>
        </nav>
      );
    case "kicker":
      return (
        <div className={`uv-kicker-demo uv-kicker-demo--${variantId}`}>
          <p className="uv-kicker-line">
            {variantId === "slash-comment"
              ? "// foundations"
              : variantId === "upper-track"
                ? "THE AGENT RUNTIME"
                : "Foundations"}
          </p>
          <p className="uv-kicker-title">Section title.</p>
        </div>
      );
    case "hero":
      return (
        <div className={`uv-hero uv-hero--${variantId}`}>
          <div className="uv-hero-copy">
            <p className="uv-hero-h">Build agents that stay up.</p>
            <p className="uv-hero-p">Claim, one CTA, proof.</p>
            {variantId === "claim-curl" ? (
              <code className="uv-curl">$ curl -fsSL … | sh</code>
            ) : null}
          </div>
          {variantId === "split-live" || variantId === "claim-mesh" ? (
            <div className="uv-hero-proof" aria-hidden="true">
              <span>❯ bun run dev</span>
              <span>ready on :4013</span>
            </div>
          ) : null}
          {variantId === "mono-center" ? (
            <div className="uv-hero-icons" aria-hidden="true">
              <span>MANUAL</span>
              <span>ISO</span>
              <span>GITHUB</span>
            </div>
          ) : null}
        </div>
      );
    case "density":
      return (
        <div className={`uv-density uv-density--${variantId}`}>
          <div />
          <div />
          <div />
        </div>
      );
    case "surfaces":
      return (
        <div className={`uv-surface uv-surface--${variantId}`}>
          <span>Surface</span>
          <span className="uv-surface-meta">hairline · flat</span>
        </div>
      );
    case "stats":
      return (
        <div className={`uv-stats uv-stats--${variantId}`}>
          {variantId === "none" ? (
            <span className="uv-stats-empty">no strip</span>
          ) : (
            <>
              <div>
                <b>33k</b>
                <i>stars</i>
              </div>
              <div>
                <b>626k</b>
                <i>installs</i>
              </div>
              <div>
                <b>21</b>
                <i>agents</i>
              </div>
            </>
          )}
        </div>
      );
    case "inputs":
      return (
        <label className={`uv-field uv-field--${variantId}`}>
          <span>API key</span>
          <input readOnly defaultValue="dgk_live_…" />
        </label>
      );
    case "docs-control":
      return (
        <div className="uv-demo-row">
          <span className="uv-cta uv-cta--white-rect">Start</span>
          <span className={`uv-docs uv-docs--${variantId}`}>Docs</span>
        </div>
      );
    default:
      return <span>{variantId}</span>;
  }
}
