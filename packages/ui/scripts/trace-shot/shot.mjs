// Open every row of the harness trace and screenshot it, printing each
// caret's computed transform and every ancestor that adds a transform.
//   node packages/ui/scripts/trace-shot/shot.mjs [outDir=/tmp/trace-shot] [dark|light] [scale=2]
// Run build.mjs first. Local Chromium via Playwright; no network, no model.
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";

const outDir = process.argv[2] || "/tmp/trace-shot";
const theme = process.argv[3] || "dark";
const scale = Number(process.argv[4] || 2);
mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({
  deviceScaleFactor: scale,
  viewport: { width: 760, height: 900 },
});
await page.goto("file://" + new URL("./index.html", import.meta.url).pathname);
await page.evaluate((t) => {
  const root = document.documentElement;
  root.setAttribute("data-theme", t);
  root.classList.toggle("light", t === "light");
  root.classList.toggle("dark", t === "dark");
}, theme);
await page.waitForSelector('[data-slot="aui_work-chain-trigger"]');

// Open every row, outermost first, re-querying as new rows mount.
for (const slot of [
  "aui_work-chain-trigger",
  "reasoning-trigger",
  "tool-group-trigger",
  "tool-fallback-trigger",
]) {
  for (let i = 0; i < 6; i++) {
    const closed = await page.$(`[data-slot="${slot}"][aria-expanded="false"]`);
    if (!closed) break;
    await closed.click();
    await page.waitForTimeout(50);
  }
}
// Let every caret transition finish.
await page.evaluate(() =>
  Promise.all(
    [
      ...document.querySelectorAll(
        '[data-slot="disclosure-chevron"] [data-slot="dot-matrix-grid"]',
      ),
    ].flatMap((el) => el.getAnimations().map((a) => a.finished)),
  ),
);
await page.waitForTimeout(400);

const rows = await page.evaluate(() =>
  [...document.querySelectorAll('[data-slot="disclosure-chevron"]')].map((caret) => {
    const trigger = caret.parentElement;
    const grid = caret.querySelector('[data-slot="dot-matrix-grid"]');
    const cs = getComputedStyle(grid);
    const chain = [];
    for (let el = grid; el && el !== document.body; el = el.parentElement) {
      const t = getComputedStyle(el).transform;
      if (t !== "none") chain.push(`${el.getAttribute("data-slot")}:${t}`);
    }
    return {
      slot: trigger.getAttribute("data-slot"),
      label: trigger.textContent.trim().slice(0, 40),
      open: trigger.getAttribute("aria-expanded"),
      transform: cs.transform,
      origin: cs.transformOrigin,
      chain,
    };
  }),
);
console.log(JSON.stringify(rows, null, 1));

await page.screenshot({ path: `${outDir}/open-trace-${theme}.png`, fullPage: true });
const row = await page.$('[data-slot="tool-fallback-trigger"]');
if (row) {
  const bb = await row.boundingBox();
  await page.screenshot({
    path: `${outDir}/tool-row-${theme}.png`,
    clip: {
      x: Math.max(0, bb.x - 8),
      y: bb.y - 8,
      width: Math.min(360, bb.width + 16),
      height: bb.height + 16,
    },
  });
}
await browser.close();
console.log(`screenshots in ${outDir}`);
