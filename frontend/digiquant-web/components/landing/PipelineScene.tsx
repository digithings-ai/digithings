"use client";
/**
 * Scroll-pinned digiquant research pipeline (ported from v7).
 *
 * One continuous, lerp-smoothed horizontal track of the REAL research phases:
 *   research  — atlas/phases/* (preflight → … → publish, 10 phases)
 *   portfolio — hermes/phases/* (h1 thesis review → … → h9 commit, 9 phases)
 *   execution — marked "In development" for live venues
 * The track stays put and pans continuously; only the engine heading crossfades
 * as scroll progress (`gp`) crosses each engine's dwell window. The rAF loop is
 * gated by an IntersectionObserver so it idles when the scene is off-screen, and
 * snaps instead of lerps under prefers-reduced-motion (still scroll-driven, no
 * autonomous motion).
 */
import { useEffect, useRef } from "react";
import { DigiquantMark } from "./OlympusMark";

type Phase = [id: string, name: string, detail: string];

// Research phases (digiquant/src/digiquant/olympus/atlas/phases/*).
const RESEARCH: Phase[] = [
  ["00", "Preflight", "config + data-layer check"],
  ["01", "Triage", "what changed since last run"],
  ["02", "Alt-data", "sentiment, flows, on-chain"],
  ["03", "Institutional", "positioning & 13F flow"],
  ["04", "Macro", "rates, liquidity, regime"],
  ["05", "Asset class", "cross-asset context"],
  ["06", "Equities", "sector & single-name"],
  ["07", "Consolidate", "merge the evidence"],
  ["08", "Synthesis", "ranked theses"],
  ["09", "Publish", "to the thesis store"],
];

// Portfolio / deliberation phases (digiquant/src/digiquant/olympus/hermes/phases/*).
const PORTFOLIO: Phase[] = [
  ["h1", "Thesis review", "inherit & re-score"],
  ["h2", "Market thesis", "exploration"],
  ["h3", "Vehicle map", "thesis → instruments"],
  ["h4", "Screener", "opportunity filter"],
  ["h5", "Asset analyst", "per-name workup"],
  ["h6", "Deliberation", "multi-agent debate"],
  ["h7", "PM direction", "allocate & gate"],
  ["h7e", "Risk sizing", "½-Kelly, ceilings"],
  ["h9", "Commit run", "persist & evolve"],
];

// The chips below render the REAL phase-folder names (atlas/phases/,
// hermes/phases/), not a display count — the h7 → h7e → h9 sequence has no h8
// because that number was never assigned a phase, not because one is
// missing. Surfaced as a title so a visitor unfamiliar with the codebase
// does not read the gap as a typo or broken enumeration (full-UI-suite
// critique, digiquant-web target, P3).
const PHASE_ID_TITLE =
  "The real internal phase-folder name, not a sequential count — a gap (like the missing h8) means that number was never assigned, not a typo.";

const NODES: [num: string, label: string][] = [
  ["01", "Research"],
  ["02", "Portfolio"],
  ["03", "Execution"],
];

const HEADS: [tag: string, h: string, p: string][] = [
  [
    "01 — Research",
    "Reads the market into ranked, sourced theses.",
    "Ten phases turn alt-data, institutional flow and macro into evidence-linked theses — every claim traceable to its source.",
  ],
  [
    "02 — Portfolio",
    "Debates the thesis, sizes the conviction.",
    "Thesis review to committed run — multi-agent deliberation, PM direction and risk sizing, with the dissent on record.",
  ],
  [
    "03 — Execution",
    "The stage after the book is committed.",
    "Paper routing exists; live venue cutover stays human-gated. Broker adapters that are not wired raise NotImplementedError.",
  ],
];

const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));

export function PipelineScene() {
  const scrollyRef = useRef<HTMLDivElement>(null);
  const stepsRef = useRef<HTMLDivElement>(null);
  const railFillRef = useRef<HTMLDivElement>(null);
  const spacerRef = useRef<HTMLDivElement>(null);
  const logoBgRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const scrolly = scrollyRef.current;
    const steps = stepsRef.current;
    const railFill = railFillRef.current;
    const spacer = spacerRef.current;
    if (!scrolly || !steps || !railFill || !spacer) return;

    const cards = Array.from(steps.children) as HTMLElement[];
    const nodes = Array.from(scrolly.querySelectorAll<HTMLElement>(".dqp-node"));
    const heads = Array.from(scrolly.querySelectorAll<HTMLElement>(".dqp-ehead"));
    const logoBg = logoBgRef.current;

    let vw = 0;
    let maxPan = 0;
    let targetPan = 0;
    let curPan = 0;
    let gp = 0;
    // per-card centre offset (real geometry, px from track start) — the pan
    // centres a card by its actual width, not a uniform-width estimate, so the
    // wide "in development" and dashboard-link cards land dead-centre too.
    let centers: number[] = [];

    function measure() {
      const track = steps!.parentElement as HTMLElement;
      vw = track.clientWidth;
      // measure real card centres with the spacer collapsed (it trails the last
      // card, so it never shifts any card's offsetLeft).
      spacer!.style.width = "0px";
      centers = cards.map((c) => c.offsetLeft + c.offsetWidth / 2);
      // size the trailing spacer so the LAST real card (the dashboard link) can
      // pan to the focus line and dwell there
      const lastCenter = centers[cards.length - 2];
      const wantScroll = lastCenter + vw * 0.5;
      spacer!.style.width = Math.max(0, Math.round(wantScroll - steps!.scrollWidth)) + "px";
      maxPan = Math.max(0, steps!.scrollWidth - vw);
    }

    // real card indices per engine (group dividers / spacer excluded)
    const byEng: Record<number, number[]> = { 0: [], 1: [], 2: [] };
    cards.forEach((c, i) => {
      const e = Number(c.dataset.eng);
      if (e >= 0 && !c.classList.contains("dqp-spacer")) byEng[e].push(i);
    });
    const A = byEng[0];
    const H = byEng[1];
    // Execution leg spans the "in development" card AND the trailing dashboard link,
    // so the pan ends by centring the link as the final beat (Kend), passing the
    // execution card on the way.
    const Kend = byEng[2][byEng[2].length - 1];
    const Aend = A[A.length - 1];
    const Hend = H[H.length - 1];

    // dwell windows: research 0–.42, portfolio .42–.80, execution .80–1
    function frontierCf(g: number) {
      if (g < 0.42) return A[0] + (g / 0.42) * (Aend - A[0]);
      if (g < 0.8) return H[0] + ((g - 0.42) / 0.38) * (Hend - H[0]);
      return Hend + ((g - 0.8) / 0.2) * (Kend - Hend);
    }

    // Discrete state (engine lit, rail fill, active head/node) is scroll-driven so
    // it stays correct even when rAF is throttled or motion is reduced. Only the
    // smooth horizontal pan is lerped in rAF, and only for motion-safe users.
    const animate = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    function applyState() {
      const rect = scrolly!.getBoundingClientRect();
      const total = scrolly!.offsetHeight - window.innerHeight;
      gp = clamp(-rect.top / (total || 1), 0, 1);
      railFill!.style.transform = `scaleX(${gp})`;
      // kinetic 3D digiquant mark behind the scene — fades in then keeps growing
      if (logoBg) {
        const lt = document.documentElement.getAttribute("data-theme") === "light";
        logoBg.style.opacity = String(clamp(gp / 0.12, 0, 1) * (lt ? 0.1 : 0.16));
        logoBg.style.transform = `perspective(900px) rotateX(20deg) scale(${0.82 + gp * 0.5})`;
      }
      const cf = frontierCf(gp);
      // centre the current/highlighted card: interpolate its real centre offset
      // between the two bracketing cards, then pan so that lands at mid-track.
      const i0 = clamp(Math.floor(cf), 0, centers.length - 1);
      const i1 = clamp(i0 + 1, 0, centers.length - 1);
      const cp = centers[i0] + (centers[i1] - centers[i0]) * (cf - i0);
      targetPan = clamp(cp - vw * 0.5, 0, maxPan);
      const fIdx = Math.round(cf);
      const activeEng = gp < 0.42 ? 0 : gp < 0.8 ? 1 : 2;
      cards.forEach((c, i) => {
        const e = Number(c.dataset.eng);
        c.classList.toggle("lit", e >= 0 && i <= fIdx);
        c.classList.toggle("cur", i === fIdx && e >= 0);
      });
      nodes.forEach((n, i) => n.classList.toggle("on", i <= activeEng));
      heads.forEach((h, i) => h.classList.toggle("show", i === activeEng));
      if (!animate) {
        curPan = targetPan; // snap; no autonomous motion
        steps!.style.transform = "translate3d(" + -curPan + "px,0,0)";
      }
    }

    let raf = 0;
    let running = false;
    function loop() {
      curPan += (targetPan - curPan) * 0.1; // buttery continuous pan
      steps!.style.transform = "translate3d(" + -curPan + "px,0,0)";
      raf = requestAnimationFrame(loop);
    }
    function start() {
      if (running || !animate) return;
      running = true;
      raf = requestAnimationFrame(loop);
    }
    function stop() {
      running = false;
      if (raf) cancelAnimationFrame(raf);
      raf = 0;
    }

    const onScroll = () => applyState();
    const onResize = () => {
      measure();
      applyState();
    };

    measure();
    applyState();
    curPan = targetPan;
    steps.style.transform = "translate3d(" + -curPan + "px,0,0)";

    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onResize, { passive: true });

    // run the pan loop only while the scene is on screen (motion-safe only)
    const io = new IntersectionObserver(
      (entries) => entries.forEach((e) => (e.isIntersecting ? start() : stop())),
      { threshold: 0 },
    );
    io.observe(scrolly);

    return () => {
      stop();
      io.disconnect();
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onResize);
    };
  }, []);

  return (
    <section className="dq-olympus" id="desk">
      <span id="olympus" className="sr-only" aria-hidden="true" />
      <div className="dqp-scrolly" ref={scrollyRef}>
        <div className="dqp-pin">
          <div className="dqp-logo-bg" aria-hidden="true" ref={logoBgRef}>
            <DigiquantMark size={560} />
          </div>
          <div className="wrap">
          <div className="dqp-scene-head">
            <div className="dqp-olympus">
              <DigiquantMark size={22} />
              <span>digiquant · research → portfolio</span>
            </div>
            <div className="dqp-scene-title">The research desk in a box.</div>
          </div>

          {/* Graphite-style progress rail (#1215): scroll-synced .dqp-fill + engine
              nodes lit in --accent as `gp` advances (see applyState). Reduced-motion-safe
              (discrete state is scroll-driven, not rAF-gated) and mobile-simplified at the
              820px breakpoint — #1215 is satisfied here, not via a separate ScrollyFeatures
              refactor of this hand-tuned scene.
              (Shared-rail evaluation, #1417: @digithings/web's ScrollyRail renders
              discrete ticks with one `.on` index; this rail is a continuous width
              fill plus numbered, labelled nodes lit cumulatively over UNEQUAL dwell
              windows (0.42/0.38/0.20) that also drive the pan math — not
              behavior-identical, and adopting useScrollyFeatures would rewrite the
              scene's scrubbing internals, which are out of scope. Left as-is.) */}
          <div className="dqp-rail">
            <div className="dqp-fill" ref={railFillRef} />
            {NODES.map(([num, label], i) => (
              <div className="dqp-node" data-i={i} key={num}>
                <div className="dqp-dot">{num}</div>
                <div className="dqp-lab">{label}</div>
              </div>
            ))}
          </div>

          <div className="dqp-heads">
            {HEADS.map(([tag, h, p], i) => (
              <div className={`dqp-ehead${i === 0 ? " show" : ""}`} data-i={i} key={tag}>
                <div className="dqp-etag">{tag}</div>
                <h3>{h}</h3>
                <p>{p}</p>
              </div>
            ))}
          </div>

          <div className="dqp-track">
            <div className="dqp-steps" ref={stepsRef}>
              <div className="dqp-step dqp-group" data-eng="-1">
                <span>Research</span>
              </div>
              {RESEARCH.map(([id, n, d]) => (
                <div className="dqp-step" data-eng="0" key={`a-${id}`}>
                  <div className="dqp-si" title={PHASE_ID_TITLE}>{id}</div>
                  <div className="dqp-sn">{n}</div>
                  <div className="dqp-sd">{d}</div>
                </div>
              ))}
              <div className="dqp-step dqp-group" data-eng="-1">
                <span>Portfolio</span>
              </div>
              {PORTFOLIO.map(([id, n, d]) => (
                <div className="dqp-step" data-eng="1" key={`h-${id}`}>
                  <div className="dqp-si" title={PHASE_ID_TITLE}>{id}</div>
                  <div className="dqp-sn">{n}</div>
                  <div className="dqp-sd">{d}</div>
                </div>
              ))}
              <div className="dqp-step dqp-group" data-eng="-1">
                <span>Execution</span>
              </div>
              <div className="dqp-step dqp-sooncard" data-eng="2">
                <span className="dqp-badge">In development</span>
                <p>Research and portfolio run today. Live execution is next.</p>
              </div>
              {/* Final beat of the horizontal track: after the pipeline pans by,
                  a quiet text+arrow that launches the dashboard. `/olympus/` is the
                  separate dashboard export (dist/olympus/), so a plain <a> (full
                  cross-app navigation), not a Next <Link>. data-eng="2" ties it to
                  the execution leg so the pan centres it last (Kend). */}
              <a className="dqp-step dqp-golink" data-eng="2" href="/olympus/">
                <span className="dqp-golink-label">Open the digiquant dashboard</span>
                <span className="dqp-golink-arrow" aria-hidden="true">→</span>
              </a>
              <div className="dqp-step dqp-spacer" data-eng="-1" aria-hidden="true" ref={spacerRef} />
            </div>
          </div>
        </div>
        </div>
      </div>
    </section>
  );
}

/** @deprecated Use PipelineScene. One-release alias (ADR-0026 wave 3). */
export const OlympusScene = PipelineScene;
