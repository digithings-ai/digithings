/**
 * digiquant.io — landing wiring. Foundation behaviour + quant flourishes:
 * a synthesized ticker and count-up tear-sheet metrics.
 */
import { initTheme } from "../design/site/theme.js";
import { initNav } from "../design/site/ui.js";
import { initReveal } from "../design/site/reveal.js";
import { initTicker } from "../design/quant-native/ticker.js";

initTheme();
initNav();
initReveal();

/* synthesized ticker (illustrative) */
try {
  initTicker({
    elementId: "dq-ticker",
    cadence: 48,
    symbols: [
      { sym: "ATLAS", price: "184.22", delta: "+0.42%" },
      { sym: "HERMES", price: "96.10", delta: "-0.18%" },
      { sym: "KAIROS", price: "212.74", delta: "+1.04%" },
      { sym: "BTC-USD", price: "68,940", delta: "+2.11%" },
      { sym: "ETH-USD", price: "3,612", delta: "-0.63%" },
      { sym: "SOL-USD", price: "184.9", delta: "+3.27%" },
      { sym: "DGQ-COMP", price: "1.184", delta: "+0.84%" },
    ],
  });
} catch (e) {}

/* count-up metrics when they scroll into view */
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
const countEls = document.querySelectorAll("[data-count]");
function runCount(el) {
  const target = parseFloat(el.dataset.count);
  if (Number.isNaN(target)) return;
  const decimals = (el.dataset.count.split(".")[1] || "").length;
  const suffix = /%$/.test(el.textContent) ? "%" : "";
  const dur = 1100;
  let start = null;
  const tick = (t) => {
    if (start === null) start = t;
    const p = Math.min((t - start) / dur, 1);
    const eased = 1 - Math.pow(1 - p, 3);
    el.textContent = (target * eased).toFixed(decimals) + suffix;
    if (p < 1) requestAnimationFrame(tick);
    else el.textContent = target.toFixed(decimals) + suffix;
  };
  requestAnimationFrame(tick);
}
if (countEls.length && !reduce && "IntersectionObserver" in window) {
  const cio = new IntersectionObserver((entries, obs) => {
    entries.forEach((entry) => { if (entry.isIntersecting) { runCount(entry.target); obs.unobserve(entry.target); } });
  }, { threshold: 0.6 });
  countEls.forEach((el) => cio.observe(el));
}
