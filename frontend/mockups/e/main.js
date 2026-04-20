/* Mockup E — Monumental
   - Typewriter hero sub-line
   - Slab reveal on scroll (IntersectionObserver)
   - Staggered schematic entry
   - Spine active state
   - Ecosystem toggle (Plug / MCP / Docker)
*/
(function () {
  "use strict";

  // Mark JS available (graceful degrade hook)
  document.documentElement.classList.remove("no-js");
  document.documentElement.classList.add("has-js");

  const prefersReducedMotion =
    window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---------------------------------------------------------------------
  // Typewriter — placeholder only
  // ---------------------------------------------------------------------
  function typewriter() {
    const host = document.querySelector("[data-typewriter]");
    if (!host) return;
    const full = host.textContent.trim();
    if (prefersReducedMotion) {
      host.textContent = full;
      return;
    }
    host.textContent = "";
    let i = 0;
    const step = () => {
      if (i <= full.length) {
        host.textContent = full.slice(0, i);
        i += 1;
        setTimeout(step, 22 + Math.random() * 24);
      }
    };
    setTimeout(step, 500);
  }

  // ---------------------------------------------------------------------
  // Schematic stagger — compute per-shape delay once
  // ---------------------------------------------------------------------
  function prepareSchematicStagger() {
    document.querySelectorAll(".schematic").forEach((svg) => {
      const shapes = svg.querySelectorAll(".shape");
      shapes.forEach((s, idx) => {
        s.style.setProperty("--d", `${idx * 90}ms`);
      });
    });
    document.querySelectorAll(".altarpiece").forEach((svg) => {
      const shapes = svg.querySelectorAll(".shape");
      shapes.forEach((s, idx) => {
        s.style.setProperty("--d", `${idx * 40}ms`);
      });
    });
  }

  // ---------------------------------------------------------------------
  // Slab reveal
  // ---------------------------------------------------------------------
  function slabReveal() {
    const slabs = document.querySelectorAll(".slab");
    if (!("IntersectionObserver" in window)) {
      slabs.forEach((s) => s.classList.add("is-visible"));
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add("is-visible");
          }
        });
      },
      { threshold: 0.22, rootMargin: "0px 0px -10% 0px" }
    );
    slabs.forEach((s) => io.observe(s));
  }

  // ---------------------------------------------------------------------
  // Spine active state
  // ---------------------------------------------------------------------
  function spineTracker() {
    const bars = document.querySelectorAll(".spine-bar");
    if (!bars.length) return;
    const sections = Array.from(document.querySelectorAll(".slab"));
    if (!("IntersectionObserver" in window)) return;

    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            const idx = sections.indexOf(e.target);
            bars.forEach((b, i) => b.classList.toggle("is-active", i === idx));
          }
        });
      },
      { threshold: 0.5 }
    );
    sections.forEach((s) => io.observe(s));

    bars.forEach((bar) => {
      bar.addEventListener("click", (ev) => {
        ev.preventDefault();
        const href = bar.getAttribute("href");
        const target = href && document.querySelector(href);
        if (target) {
          target.scrollIntoView({
            behavior: prefersReducedMotion ? "auto" : "smooth",
            block: "start",
          });
        }
      });
    });
  }

  // ---------------------------------------------------------------------
  // Ecosystem toggles
  // ---------------------------------------------------------------------
  function ecosystem() {
    const toggles = document.querySelectorAll(".ecosystem-toggles .toggle");
    const canvas = document.querySelector(".ecosystem-canvas");
    const legends = document.querySelectorAll(".ecosystem-legend [data-legend]");
    if (!toggles.length || !canvas) return;

    toggles.forEach((t) => {
      t.addEventListener("click", () => {
        const mode = t.getAttribute("data-mode");
        toggles.forEach((o) => {
          const on = o === t;
          o.classList.toggle("is-active", on);
          o.setAttribute("aria-selected", on ? "true" : "false");
        });
        canvas.setAttribute("data-mode", mode);
        legends.forEach((p) => {
          p.hidden = p.getAttribute("data-legend") !== mode;
        });
      });
    });
  }

  // ---------------------------------------------------------------------
  // Boot
  // ---------------------------------------------------------------------
  function boot() {
    prepareSchematicStagger();
    typewriter();
    slabReveal();
    spineTracker();
    ecosystem();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
