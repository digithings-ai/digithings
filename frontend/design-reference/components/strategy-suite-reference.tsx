"use client";

import { useRef, useState } from "react";
import { useMotionValueEvent, useScroll, useReducedMotion } from "motion/react";

type StrategyCard = { name: string; summary: string; cagr: string; maxDd: string; pf: string };

const CARDS: StrategyCard[] = [
  {
    name: "BTC Slapper",
    summary: "Trend-following, 1D bars, long/short.",
    cagr: "+44.9%",
    maxDd: "-54.1%",
    pf: "2.31",
  },
  {
    name: "ETH Slapper",
    summary: "Cross-regime momentum with flat-state guard.",
    cagr: "+38.1%",
    maxDd: "-49.7%",
    pf: "2.12",
  },
  {
    name: "SOL Slapper",
    summary: "Higher-volatility profile with tighter risk cap.",
    cagr: "+52.4%",
    maxDd: "-59.2%",
    pf: "2.58",
  },
];

export function StrategySuiteReference() {
  const sectionRef = useRef<HTMLElement | null>(null);
  const reduced = useReducedMotion();
  const [active, setActive] = useState(0);

  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start center", "end center"],
  });

  useMotionValueEvent(scrollYProgress, "change", (progress) => {
    if (reduced) {
      setActive(CARDS.length - 1);
      return;
    }
    const idx = Math.min(CARDS.length - 1, Math.max(0, Math.floor(progress * CARDS.length)));
    setActive(idx);
  });

  return (
    <section className="section-block strategy-scrolly" id="strategy-suite" ref={sectionRef}>
      <div className="section-head">
        <p className="kicker">{"// strategy suite"}</p>
        <h2 className="title">Sticky peek stack + rail, React-native.</h2>
      </div>

      <div className="strategy-track">
        <div className="strategy-pin">
          <div className="strategy-stack" role="list" aria-label="Strategy tearsheet stack">
            {CARDS.map((card, idx) => {
              const isPast = idx <= active;
              const y = reduced ? 0 : isPast ? 0 : 132;
              return (
                <article
                  key={card.name}
                  role="listitem"
                  className="strategy-card"
                  style={{
                    top: `calc(var(--peek) * ${idx})`,
                    transform: `translate3d(0, ${y}px, 0)`,
                    zIndex: CARDS.length - idx,
                  }}
                  aria-hidden={!reduced && idx > active}
                >
                  <div className="strategy-card-head">
                    <h3>{card.name}</h3>
                    <span>{idx + 1}</span>
                  </div>
                  <p>{card.summary}</p>
                  <dl>
                    <div>
                      <dt>CAGR</dt>
                      <dd className="up">{card.cagr}</dd>
                    </div>
                    <div>
                      <dt>Max DD</dt>
                      <dd className="down">{card.maxDd}</dd>
                    </div>
                    <div>
                      <dt>Profit factor</dt>
                      <dd>{card.pf}</dd>
                    </div>
                  </dl>
                </article>
              );
            })}
          </div>

          <ol className="strategy-rail" aria-label="Stack progress">
            {CARDS.map((card, idx) => (
              <li key={card.name} className={idx === active ? "on" : undefined}>
                <span className="dot" />
                <span className="name">{card.name}</span>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}
