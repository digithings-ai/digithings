"use client";

import { useRef, useState } from "react";
import { m, useReducedMotion, useScroll, useTransform } from "motion/react";

const COLUMNS = [
  { title: "Product", links: ["digigraph", "digiquant", "digisearch", "digichat"] },
  { title: "Company", links: ["About", "Careers", "Blog"] },
  { title: "Resources", links: ["Docs", "Changelog", "Status"] },
  { title: "Connect", links: ["GitHub", "Discord", "X"] },
];

const THEMES = ["System", "Light", "Dark"] as const;

/**
 * Footer & chrome — utility link columns, a status/theme/copyright row, and the
 * one sanctioned personality moment: an ambient bloom under a giant outlined
 * colophon. Scroll into it and an accent glow sweeps left→right across the
 * wordmark, scrubbed by the colophon's own scroll progress; reduced motion
 * parks the sweep off-screen so no glow travels.
 */
export function FooterReference() {
  const [theme, setTheme] = useState<(typeof THEMES)[number]>("System");
  const brandRef = useRef<HTMLDivElement | null>(null);
  const reduced = useReducedMotion();

  // Drive the glow from the colophon's own scroll progress. offset
  // ["start end", "end end"] is fully reachable even though the colophon is
  // the last thing on the page (0 = its top enters the viewport bottom,
  // 1 = scrolled to the very bottom). The band travels off-left → off-right,
  // so the highlight sweeps across the wordmark once as you scroll into it.
  const { scrollYProgress } = useScroll({
    target: brandRef,
    offset: ["start end", "end end"],
  });
  // With the brand box's bottom runway, its scroll progress spreads the
  // wordmark's fully-visible window across the middle of the range — so the
  // band crosses (≈120%→0%) while the sign is on screen, not below the fold.
  const sweepPos = useTransform(scrollYProgress, [0.38, 0.96], [120, -20]);
  const backgroundPosition = useTransform(sweepPos, (v) => `${v}% 0`);

  return (
    <section className="section-block footer-ref">
      <p className="kicker">{"// footer & chrome"}</p>
      <h2 className="title">Utility rows, one personality moment.</h2>
      <p className="section-copy">
        The footer is the one sanctioned zone for color play — an ambient bloom under the colophon,
        the brand name at giant outlined scale as the page&apos;s last word. Scroll into it and an
        accent glow sweeps left to right across the wordmark, scrubbed by the colophon&apos;s own
        scroll progress. Everywhere else stays hairline.
      </p>

      <footer className="mt-[1.2rem] overflow-hidden rounded-[12px] border border-hair px-[1.4rem] pt-[1.4rem]">
        <div className="grid grid-cols-4 gap-[0.8rem] max-[900px]:grid-cols-2">
          {COLUMNS.map((col) => (
            <div key={col.title}>
              <p className="text-[0.78rem] text-ink">{col.title}</p>
              <ul className="m-0 mt-[0.6rem] flex list-none flex-col gap-[0.45rem] p-0">
                {col.links.map((link) => (
                  <li key={link} className="text-[0.76rem] text-ink-mute">
                    {link}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-[1.2rem] flex flex-wrap items-center gap-[1rem] border-t border-hair py-[0.9rem] font-mono text-[0.68rem]">
          <span className="inline-flex items-center gap-[0.4rem] text-ink-soft">
            <span className="status-dot" aria-hidden="true" />
            All systems operational
          </span>

          <span className="ref-footer-theme" role="group" aria-label="Theme">
            {THEMES.map((option) => (
              <button
                key={option}
                type="button"
                className={option === theme ? "on" : ""}
                onClick={() => setTheme(option)}
                aria-pressed={option === theme}
              >
                {option}
              </button>
            ))}
          </span>

          <span className="ml-auto text-ink-mute">© 2026 digithings · SOC 2 in progress</span>
        </div>

        {/* Colophon — the page's last word (canon §08): the brand at giant
            scale, 1px hairline outline. The accent glow sweeps left→right
            across it, scrubbed by the colophon's scroll progress (Motion).
            Reduced motion parks the band off-screen so no glow travels.
            aria-hidden: punctuation, not content — the accessible brand name
            lives in the utility-row copyright. */}
        <div className="ref-footer-brand" ref={brandRef}>
          <span className="ref-footer-bloom" aria-hidden="true" />
          <div className="ref-colophon" aria-hidden="true">
            <span className="ref-colo-word">
              digi<b>things</b>
              <m.span
                className="ref-colo-sweep"
                style={reduced ? undefined : { backgroundPosition }}
              >
                digithings
              </m.span>
            </span>
          </div>
        </div>
      </footer>
    </section>
  );
}
