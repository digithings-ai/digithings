// DIG-3446 deep probe: overflow offenders, contrast targets, canvas labels,
// article roles, hero-chart attr, region. Usage: node probe.mjs
import { createRequire } from "node:module";
const require = createRequire(process.env.WT + "/package.json");
const { chromium } = require("playwright");
const PORT = process.env.DQPORT || "5223";
const browser = await chromium.launch();
const out = {};
for (const [id, url, vw] of [
  ["pipeline-m", `http://127.0.0.1:${PORT}/pipeline/`, { width: 390, height: 844 }],
  ["pipeline-d", `http://127.0.0.1:${PORT}/pipeline/`, { width: 1440, height: 900 }],
  ["home-m", `http://127.0.0.1:${PORT}/`, { width: 390, height: 844 }],
]) {
  const ctx = await browser.newContext({ viewport: vw, deviceScaleFactor: 1, colorScheme: "dark" });
  const page = await ctx.newPage();
  await page.goto(url, { waitUntil: "load", timeout: 120000 });
  await page.waitForTimeout(2500);
  out[id] = await page.evaluate(() => {
    const cs = (el) => getComputedStyle(el);
    const vw = window.innerWidth;
    const wide = [];
    for (const el of document.querySelectorAll("body *")) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) continue;
      if (r.right > vw + 1) {
        const kids = [...el.children].filter((c) => c.getBoundingClientRect().right > vw + 1);
        if (kids.length === 0) {
          wide.push(`${el.tagName}.${(el.className.baseVal ?? el.className ?? "").toString().split(" ").slice(0, 3).join(".")} right=${Math.round(r.right)} w=${Math.round(r.width)} txt=${(el.textContent || "").trim().slice(0, 40)}`);
        }
      }
    }
    const canvases = [...document.querySelectorAll("canvas")].map((c) => ({
      label: c.getAttribute("aria-label") || null,
      hidden: c.getAttribute("aria-hidden") || (c.closest("[aria-hidden=true]") ? "ancestor" : null),
      cls: (c.className || "").toString().slice(0, 60),
      box: (() => { const r = c.getBoundingClientRect(); return `${Math.round(r.width)}x${Math.round(r.height)}`; })(),
      parent: c.parentElement ? `${c.parentElement.tagName}.${(c.parentElement.className || "").toString().split(" ").slice(0, 2).join(".")}` : "?",
    }));
    const articles = [...document.querySelectorAll("article")].map((a) => ({
      role: a.getAttribute("role") || "(none)",
      aria: a.getAttribute("aria-label") || a.getAttribute("aria-labelledby") || "(none)",
      cls: (a.className || "").toString().split(" ").slice(0, 3).join("."),
    }));
    const hero = document.querySelector(".hero-chart");
    const asides = [...document.querySelectorAll("aside")].map((a) => ({
      label: a.getAttribute("aria-label") || "(none)",
      cls: (a.className || "").toString().slice(0, 60),
      context: a.closest("main") ? "in-main" : "top-level",
    }));
    const h1s = [...document.querySelectorAll("h1")].map((h) => {
      let p = h.parentElement, path = [];
      while (p && path.length < 4) { path.push(`${p.tagName}.${(p.className || "").toString().split(" ").slice(0, 2).join(".")}`); p = p.parentElement; }
      return `${h.textContent.trim().slice(0, 30)} <= ${path.join(" < ")}`;
    });
    // animation census by target
    const animBy = {};
    for (const a of document.getAnimations()) {
      const t = a.effect && a.effect.target;
      const key = t ? `${t.tagName}.${(t.className || "").toString().split(" ").slice(0, 2).join(".")}` : "(no-target)";
      animBy[key] = (animBy[key] || 0) + 1;
    }
    const top = Object.entries(animBy).sort((a, b) => b[1] - a[1]).slice(0, 12);
    return {
      scrollW: document.documentElement.scrollWidth, innerW: vw,
      wide: wide.slice(0, 12), wideCount: wide.length,
      canvases, articles,
      heroChart: hero ? { role: hero.getAttribute("role"), ariaLabel: hero.getAttribute("aria-label"), tabIndex: hero.getAttribute("tabindex") } : null,
      asides, h1s, topAnims: top, totalAnims: document.getAnimations().length,
    };
  });
  console.log(`== ${id} == scrollW=${out[id].scrollW} wide=${out[id].wideCount} anims=${out[id].totalAnims}`);
  for (const w of out[id].wide) console.log("  WIDE:", w);
  console.log("  canvases:", JSON.stringify(out[id].canvases.slice(0, 22)));
  console.log("  articles:", JSON.stringify(out[id].articles.slice(0, 8)));
  console.log("  hero:", JSON.stringify(out[id].heroChart), "asides:", JSON.stringify(out[id].asides));
  console.log("  h1s:", JSON.stringify(out[id].h1s));
  console.log("  topAnims:", JSON.stringify(out[id].topAnims));
  await ctx.close();
}
await browser.close();
