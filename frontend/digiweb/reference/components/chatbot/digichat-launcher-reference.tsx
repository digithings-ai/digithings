"use client";

/**
 * Digichat launcher — the reusable compact entry point for embedding digichat
 * over a product surface: square terminal mark at rest, typed wordmark on
 * hover/focus, and a two-step in-place expansion with outside-click dismissal.
 */
import { DigichatLauncher } from "@digithings/web";
import type { CSSProperties } from "react";

export function DigichatLauncherReference() {
  return (
    <section className="section-block">
      <p className="kicker">{"// embedded launcher"}</p>
      <h2 className="title">A chat entry point, not a floating billboard.</h2>
      <p className="section-copy">
        The idle control is a perfect 30-pixel square using the canonical compact
        terminal mark. Hover or focus types <code>digichat</code> without changing
        its height or border. Clicking expands it in two steps from that corner —
        sideways into a composer-height bar, then upward to full height — and the
        header close button, Escape, or a click outside reverses both. The host
        page stays sharp throughout.
      </p>

      <div className="dcl-reference-stage">
        <div className="dcl-reference-copy" aria-hidden="true">
          <span>{"// dashboard context"}</span>
          <strong>WHAT MATTERS NOW</strong>
          <p>
            One reusable launcher can host the digichat embed on dashboard,
            digiquant, and future product surfaces.
          </p>
        </div>

        <DigichatLauncher
          portal={false}
          ariaLabel="digichat launcher specimen"
          style={{
            "--digichat-launcher-panel-width": "min(340px, calc(100vw - 4rem))",
            "--digichat-launcher-panel-height": "320px",
          } as CSSProperties}
        >
          <div className="dcl-reference-chat">
            <p className="dcl-reference-status">connected · page context attached</p>
            <div>
              <span>▸</span>
              <p>What would you like to inspect on this page?</p>
            </div>
            <div className="dcl-reference-composer">
              <span>&gt;</span>
              <span>Ask digichat…</span>
              <span className="dcl-reference-caret" aria-hidden="true" />
            </div>
          </div>
        </DigichatLauncher>
      </div>
    </section>
  );
}
