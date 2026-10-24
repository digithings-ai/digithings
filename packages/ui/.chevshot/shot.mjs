import { chromium } from "playwright";
const out = process.argv[2] || "/tmp/chev";
const theme = process.argv[3] || "dark";
const b = await chromium.launch();
const p = await b.newPage({ deviceScaleFactor: 2, viewport: { width: 760, height: 900 } });
await p.goto("file://" + new URL("./index.html", import.meta.url).pathname);
await p.evaluate((t) => { const e = document.documentElement; e.setAttribute("data-theme", t); e.classList.toggle("light", t === "light"); e.classList.toggle("dark", t === "dark"); }, theme);
await p.waitForSelector('[data-slot="aui_work-chain-trigger"]');
// Open every row, outermost first, re-querying as new rows mount.
for (const slot of ["aui_work-chain-trigger", "reasoning-trigger", "tool-group-trigger", "tool-fallback-trigger"]) {
  for (let i = 0; i < 6; i++) {
    const closed = await p.$(`[data-slot="${slot}"][aria-expanded="false"]`);
    if (!closed) break;
    await closed.click();
    await p.waitForTimeout(50);
  }
}
// Wait for every caret transition to finish.
await p.evaluate(() => Promise.all([...document.querySelectorAll('[data-slot="disclosure-chevron"] [data-slot="dot-matrix-grid"]')].flatMap((el) => el.getAnimations().map((a) => a.finished))));
await p.waitForTimeout(400);
const rows = await p.evaluate(() => [...document.querySelectorAll('[data-slot="disclosure-chevron"]')].map((c) => {
  const trig = c.parentElement; const g = c.querySelector('[data-slot="dot-matrix-grid"]');
  const cs = getComputedStyle(g); const r = g.getBoundingClientRect(); const cb = c.getBoundingClientRect();
  let chain = []; for (let el = g; el && el !== document.body; el = el.parentElement) { const t = getComputedStyle(el).transform; if (t !== "none") chain.push(el.getAttribute("data-slot") + ":" + t); }
  return { slot: trig.getAttribute("data-slot"), label: trig.textContent.trim().slice(0, 40), open: trig.getAttribute("aria-expanded"), transform: cs.transform, rotate: cs.rotate, origin: cs.transformOrigin, box: [cb.width, cb.height], svg: [Math.round(r.width*100)/100, Math.round(r.height*100)/100], chain };
}));
console.log(JSON.stringify(rows, null, 1));
await p.screenshot({ path: `${out}/open-trace-${theme}.png`, fullPage: true });
const dig = await p.$('[data-slot="tool-fallback-trigger"]');
if (dig) { const bb = await dig.boundingBox(); await p.screenshot({ path: `${out}/digisearch-row-${theme}.png`, clip: { x: Math.max(0, bb.x - 8), y: bb.y - 8, width: Math.min(360, bb.width + 16), height: bb.height + 16 } }); }
await b.close();
