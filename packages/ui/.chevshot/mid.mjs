import { chromium } from "playwright";
const b = await chromium.launch(); const p = await b.newPage();
await p.goto("file://" + new URL("./index.html", import.meta.url).pathname);
await p.waitForSelector('[data-slot="aui_work-chain-trigger"]');
await (await p.$('[data-slot="aui_work-chain-trigger"]')).click(); await p.waitForTimeout(300);
await (await p.$('[data-slot="tool-group-trigger"]')).click(); await p.waitForTimeout(300);
const r = await p.evaluate(() => new Promise((res) => {
  const t = document.querySelector('[data-slot="tool-fallback-trigger"]'); const g = t.querySelector('[data-slot="dot-matrix-grid"]');
  const ang = () => { const g = document.querySelector('[data-slot="tool-fallback-trigger"] [data-slot="disclosure-chevron"] [data-slot="dot-matrix-grid"]'); const m = new DOMMatrix(getComputedStyle(g).transform); return Math.round(Math.atan2(m.b, m.a) * 1800 / Math.PI) / 10; };
  const out = []; const t0 = performance.now(); let ended = null;
  document.addEventListener("transitionend", (e) => { if (e.target.getAttribute && e.target.getAttribute("data-slot")==="dot-matrix-grid") ended = Math.round(performance.now() - t0); }, { once: true });
  t.click();
  const tick = () => { out.push(Math.round(performance.now() - t0) + "ms:" + ang()); if (performance.now() - t0 < 260) requestAnimationFrame(tick); else res({ out, ended }); };
  requestAnimationFrame(tick);
}));
console.log("transitionend at", r.ended, "ms;", r.out.join(" "));
await b.close();
