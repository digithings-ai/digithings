"use client";

import { useEffect, useRef } from "react";
import { initBrandStudio } from "./studio-app";

/**
 * The composer. The controls are intentionally uncontrolled: the studio's
 * imperative initializer owns the canvas, presets, export and animation state
 * (the same logic the standalone brand builder used). React owns the shell.
 */
export function BrandStudio() {
  const rootRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    return initBrandStudio(root);
  }, []);

  return (
    <section className="bs" ref={rootRef} aria-label="Brand studio composer" aria-busy="true">
      <div className="bs-workspace">
        <aside className="bs-panel" aria-label="Brand asset controls">
          <div className="bs-section">
            <div className="bs-section-head">
              <h2>Preset</h2>
              <button className="bs-text-btn" id="bs-resetPreset" type="button" disabled>
                Reset
              </button>
            </div>
            <label className="bs-sr-only" htmlFor="bs-presetSel">
              Preset
            </label>
            <select className="bs-select" id="bs-presetSel" />
            <p className="bs-hint" id="bs-presetHint">Loading studio…</p>
          </div>

          <div className="bs-section">
            <h2>Canvas</h2>
            <div className="bs-row bs-row-top">
              <label className="bs-field">
                <span>Width</span>
                <input
                  className="bs-input"
                  id="bs-cw"
                  type="number"
                  min={16}
                  max={8192}
                  step={1}
                  defaultValue={1500}
                />
              </label>
              <label className="bs-field">
                <span>Height</span>
                <input
                  className="bs-input"
                  id="bs-ch"
                  type="number"
                  min={16}
                  max={8192}
                  step={1}
                  defaultValue={500}
                />
              </label>
            </div>

            <div className="bs-control">
              <div className="bs-control-head">
                <span>Background</span>
              </div>
              <div className="bs-seg bs-seg-4" id="bs-bgSeg" role="group" aria-label="Background">
                <button type="button" data-bg="solid" aria-pressed="true">
                  Solid
                </button>
                <button type="button" data-bg="field" aria-pressed="false">
                  Field
                </button>
                <button type="button" data-bg="field-anim" aria-pressed="false">
                  Field motion
                </button>
                <button type="button" data-bg="transparent" aria-pressed="false">
                  None
                </button>
              </div>
              <select id="bs-bgmode" hidden aria-hidden="true" tabIndex={-1} defaultValue="solid">
                <option value="solid">solid</option>
                <option value="field">field</option>
                <option value="field-anim">field animated</option>
                <option value="transparent">transparent</option>
              </select>
            </div>

            <div className="bs-control">
              <label className="bs-field" htmlFor="bs-theme">
                <span>Theme</span>
              </label>
              <select className="bs-select" id="bs-theme" />
            </div>

            <div className="bs-control">
              <div className="bs-control-head">
                <span>Mode</span>
              </div>
              <div className="bs-seg" id="bs-modeSeg" role="group" aria-label="Mode">
                <button type="button" data-mode="dark" aria-pressed="true">
                  Dark
                </button>
                <button type="button" data-mode="light" aria-pressed="false">
                  Light
                </button>
              </div>
              <select id="bs-pol" hidden aria-hidden="true" tabIndex={-1} defaultValue="dark">
                <option value="dark">dark</option>
                <option value="light">light</option>
              </select>
            </div>

            <div className="bs-control">
              <label className="bs-field" htmlFor="bs-layout">
                <span>Layout</span>
              </label>
              <select className="bs-select" id="bs-layout" defaultValue="logo-left">
                <option value="logo-left">Logo left + wordmark</option>
                <option value="stacked">Stacked</option>
                <option value="logo-only">Logo only</option>
                <option value="word-only">Wordmark only</option>
                <option value="logo-right">Wordmark + logo right</option>
              </select>
            </div>
          </div>

          <div className="bs-section" id="bs-logoSection">
            <div className="bs-section-head">
              <h2>Logo</h2>
              <label className="bs-switch bs-switch-sm" title="Show logo">
                <input type="checkbox" id="bs-logoOn" defaultChecked />
                <span className="bs-track" />
                <span className="bs-sr-only">Show logo</span>
              </label>
            </div>
            <div className="bs-section-body" id="bs-logoBody">
              <div className="bs-slider">
                <div className="bs-slider-head">
                  <label htmlFor="bs-logoS">Size</label>
                  <output id="bs-lsv">60%</output>
                </div>
                <input id="bs-logoS" type="range" min={4} max={95} step={1} defaultValue={60} />
              </div>
              <div className="bs-row">
                <div className="bs-slider">
                  <div className="bs-slider-head">
                    <label htmlFor="bs-logoX">X</label>
                    <output id="bs-lxv">50%</output>
                  </div>
                  <input
                    id="bs-logoX"
                    type="range"
                    min={-50}
                    max={150}
                    step={0.1}
                    defaultValue={50}
                  />
                </div>
                <div className="bs-slider">
                  <div className="bs-slider-head">
                    <label htmlFor="bs-logoY">Y</label>
                    <output id="bs-lyv">50%</output>
                  </div>
                  <input
                    id="bs-logoY"
                    type="range"
                    min={-50}
                    max={150}
                    step={0.1}
                    defaultValue={50}
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="bs-section" id="bs-wordSection">
            <div className="bs-section-head">
              <h2>Hero wordmark</h2>
              <label className="bs-switch bs-switch-sm" title="Show hero wordmark">
                <input type="checkbox" id="bs-wordOn" defaultChecked />
                <span className="bs-track" />
                <span className="bs-sr-only">Show hero wordmark</span>
              </label>
            </div>
            <div className="bs-section-body" id="bs-wordBody">
              <div className="bs-slider">
                <div className="bs-slider-head">
                  <label htmlFor="bs-wordS">Size</label>
                  <output id="bs-wsv">15%</output>
                </div>
                <input
                  id="bs-wordS"
                  type="range"
                  min={2}
                  max={70}
                  step={0.1}
                  defaultValue={15}
                />
              </div>
              <div className="bs-row">
                <div className="bs-slider">
                  <div className="bs-slider-head">
                    <label htmlFor="bs-wordX">X</label>
                    <output id="bs-wxv">50%</output>
                  </div>
                  <input
                    id="bs-wordX"
                    type="range"
                    min={-50}
                    max={150}
                    step={0.1}
                    defaultValue={50}
                  />
                </div>
                <div className="bs-slider">
                  <div className="bs-slider-head">
                    <label htmlFor="bs-wordY">Y</label>
                    <output id="bs-wyv">50%</output>
                  </div>
                  <input
                    id="bs-wordY"
                    type="range"
                    min={-50}
                    max={150}
                    step={0.1}
                    defaultValue={50}
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="bs-section">
            <div className="bs-section-head">
              <h2>Motion</h2>
              <label className="bs-switch bs-switch-sm" title="Animate logo and wordmark">
                <input type="checkbox" id="bs-animOn" defaultChecked />
                <span className="bs-track" />
                <span className="bs-sr-only">Animate logo and wordmark</span>
              </label>
            </div>
            <p className="bs-hint">
              Randomized pixel build, idle flicker and glints. Both layers share one state.
              Exports are still frames.
            </p>
            <div className="bs-row bs-row-top">
              <button className="bs-btn bs-btn-ghost bs-btn-sm" id="bs-replay" type="button">
                Replay
              </button>
              <button className="bs-btn bs-btn-ghost bs-btn-sm" id="bs-center" type="button">
                Center
              </button>
            </div>
          </div>
        </aside>

        <div className="bs-main">
          <div className="bs-canvas-card">
            <div className="bs-toolbar">
              <div className="bs-canvas-meta">
                <div className="bs-eyebrow">Canvas</div>
                <div className="bs-canvas-title-row" aria-live="polite">
                  <h2 className="bs-canvas-title" id="bs-canvasTitle">
                    X profile header
                  </h2>
                  <span className="bs-badge" id="bs-dirtyBadge" hidden>
                    Custom
                  </span>
                </div>
                <div className="bs-canvas-sub">
                  <span id="bs-canvasDims">1500 × 500 px</span>
                  <span className="bs-dot" />
                  <span id="bs-canvasTheme">Default · Dark</span>
                </div>
              </div>
              <div className="bs-canvas-actions">
                <label className="bs-sr-only" htmlFor="bs-pngScale">
                  PNG scale
                </label>
                <select
                  className="bs-select bs-toolbar-select"
                  id="bs-pngScale"
                  defaultValue="1"
                  title="PNG scale"
                >
                  <option value="1">1×</option>
                  <option value="2">2×</option>
                </select>
                <button className="bs-btn bs-btn-sm" id="bs-exportSvg" type="button" disabled>
                  Export SVG
                </button>
                <button
                  className="bs-btn bs-btn-primary bs-btn-sm"
                  id="bs-exportPng"
                  type="button"
                  disabled
                >
                  Export PNG
                </button>
              </div>
            </div>

            <div className="bs-canvas-area" id="bs-canvasArea">
              <div className="bs-stage" id="bs-stage" role="img" aria-label="Brand asset preview">
                <div className="bs-bg bs-solid" id="bs-bg" />
                <div className="bs-layer bs-logo" id="bs-logoLayer" aria-hidden="true" />
                <div className="bs-layer bs-word" id="bs-wordLayer" aria-hidden="true" />
              </div>
            </div>
          </div>

          <section className="bs-gallery" aria-labelledby="bs-galleryTitle">
            <div className="bs-gallery-head">
              <h2 id="bs-galleryTitle">Presets</h2>
              <span id="bs-galleryCount" />
            </div>
            <div id="bs-presetGallery" />
          </section>
        </div>
      </div>

      <div className="bs-toast" id="bs-toast" role="status" aria-live="polite" />
    </section>
  );
}
