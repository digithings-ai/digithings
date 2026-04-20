/* Mockup A — Precision editorial
 * Motion primitives: opacity, translate, font-weight, letter-spacing,
 * stroke-dashoffset. Sticky-scroll acts drive a --scroll 0..1 property.
 */
(() => {
  // Toggle no-js class off now that JS runs.
  document.documentElement.classList.remove("no-js");

  const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // --------------------------------------------------------------------
  // 1. Hero typewriter (static, three cycling queries).
  // --------------------------------------------------------------------
  const tw = document.getElementById("typewriter");
  if (tw) {
    const lines = [
      { q: "Build me a mean-reversion stat-arb on tech.", a: "→ routing → digiquant / Atlas · backtest queued." },
      { q: "Summarize our 10-K risk factors by quarter.", a: "→ routing → digisearch · 42 chunks retrieved." },
      { q: "Expose the strategy registry as MCP tools.", a: "→ routing → digigraph · 7 tools published." },
    ];
    let li = 0;
    let ci = 0;
    let mode = "type"; // type | pauseQ | typeA | pause | erase
    const speed = prefersReduced ? 0 : 34;

    const tick = () => {
      const line = lines[li];
      const full = line.q + "\n" + line.a;
      if (mode === "type") {
        ci++;
        tw.textContent = line.q.slice(0, ci);
        if (ci >= line.q.length) { mode = "pauseQ"; setTimeout(tick, 520); return; }
        setTimeout(tick, speed);
      } else if (mode === "pauseQ") {
        ci = 0; mode = "typeA"; setTimeout(tick, 120);
      } else if (mode === "typeA") {
        ci++;
        tw.textContent = line.q + "\n" + line.a.slice(0, ci);
        if (ci >= line.a.length) { mode = "pause"; setTimeout(tick, 1800); return; }
        setTimeout(tick, speed);
      } else if (mode === "pause") {
        mode = "erase"; setTimeout(tick, 200);
      } else if (mode === "erase") {
        const cur = tw.textContent;
        if (cur.length === 0) { li = (li + 1) % lines.length; ci = 0; mode = "type"; setTimeout(tick, 200); return; }
        tw.textContent = cur.slice(0, -2);
        setTimeout(tick, 10);
      }
    };
    if (prefersReduced) {
      tw.textContent = lines[0].q + "\n" + lines[0].a;
    } else {
      setTimeout(tick, 400);
    }
  }

  // --------------------------------------------------------------------
  // 2. Hero title settle: once hero enters view and user scrolls a bit,
  //    weight/tracking transition to settled state.
  // --------------------------------------------------------------------
  const heroTitle = document.querySelector(".hero-title");
  const onHeroScroll = () => {
    if (!heroTitle) return;
    const y = window.scrollY;
    if (y > 40) heroTitle.classList.add("is-settled");
    else heroTitle.classList.remove("is-settled");
  };
  onHeroScroll();
  window.addEventListener("scroll", onHeroScroll, { passive: true });

  // --------------------------------------------------------------------
  // 3. Per-act --scroll progress (0..1) driven by section geometry.
  //    Acts are 250vh tall; while the sticky child is pinned (i.e. the
  //    section's top is between 0 and section.height - viewport),
  //    progress = pinnedOffset / (height - viewport).
  // --------------------------------------------------------------------
  const acts = Array.from(document.querySelectorAll(".act"));
  const pips = Array.from(document.querySelectorAll(".pip"));

  const updateActs = () => {
    const vh = window.innerHeight;
    let activeIndex = -1;
    acts.forEach((act, i) => {
      const rect = act.getBoundingClientRect();
      const height = rect.height;
      const distance = Math.max(1, height - vh);
      // progress: 0 when act top hits viewport top, 1 when bottom - vh passes top
      let p = (-rect.top) / distance;
      p = Math.max(0, Math.min(1, p));
      act.style.setProperty("--scroll", p.toFixed(4));

      // active when section occupies majority of viewport
      if (rect.top <= vh * 0.5 && rect.bottom >= vh * 0.5) {
        activeIndex = i;
      }

      // Ecosystem panel staging for act 5
      if (act.id === "act-5") {
        act.classList.remove("eco-panel-0", "eco-panel-1", "eco-panel-2");
        let panel = 0;
        if (p < 0.34) panel = 0;
        else if (p < 0.7) panel = 1;
        else panel = 2;
        act.classList.add("eco-panel-" + panel);
        // highlight panel-index list
        const items = act.querySelectorAll(".panel-index li");
        items.forEach((el, idx) => el.classList.toggle("active", idx === panel));
      }
    });

    // pip active state
    pips.forEach((pip, i) => pip.classList.toggle("is-active", i === activeIndex));
  };

  if (prefersReduced) {
    // Set scroll to 1 so schematics render fully drawn.
    acts.forEach((act) => act.style.setProperty("--scroll", "1"));
    // Still update on scroll for pip active state, cheaply.
    window.addEventListener("scroll", () => {
      const vh = window.innerHeight;
      let activeIndex = -1;
      acts.forEach((act, i) => {
        const rect = act.getBoundingClientRect();
        if (rect.top <= vh * 0.5 && rect.bottom >= vh * 0.5) activeIndex = i;
      });
      pips.forEach((pip, i) => pip.classList.toggle("is-active", i === activeIndex));
    }, { passive: true });
  } else {
    let rafId = 0;
    const onScroll = () => {
      if (rafId) return;
      rafId = requestAnimationFrame(() => { rafId = 0; updateActs(); });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    updateActs();
  }
})();
