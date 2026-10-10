import { chromium } from "playwright";
const b = await chromium.launch();
const [base, ...paths] = process.argv.slice(2);
for (const scheme of ["light", "dark"]) for (const u of paths) {
  let n = 0;
  for (let i = 0; i < 8; i++) {
    const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });
    await ctx.addInitScript((t) => localStorage.setItem("dt-theme", t), scheme);
    await ctx.route("**/_next/static/chunks/**", async (r) => { await new Promise((s) => setTimeout(s, 500)); r.continue(); });
    const p = await ctx.newPage();
    p.on("pageerror", (e) => { if (String(e).includes("418")) n++; });
    await p.goto(base + u, { waitUntil: "networkidle" });
    await p.waitForTimeout(300);
    const th = await p.evaluate(() => document.documentElement.dataset.theme);
    if (th !== scheme) n += 0.001;
    await ctx.close();
  }
  console.log(scheme, u, n, "/ 8");
}
await b.close();
