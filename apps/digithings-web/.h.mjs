import { chromium } from "playwright";
const b = await chromium.launch();
for (const u of process.argv.slice(2)) {
  let n = 0;
  for (let i = 0; i < 4; i++) {
    const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });
    await ctx.route("**/_next/static/chunks/**", async (r) => { await new Promise((s) => setTimeout(s, 500)); r.continue(); });
    const p = await ctx.newPage();
    p.on("pageerror", (e) => { if (String(e).includes("418")) n++; });
    await p.goto("http://127.0.0.1:4050" + u, { waitUntil: "networkidle" });
    await p.waitForTimeout(400);
    await ctx.close();
  }
  console.log(u, n, "/ 4");
}
await b.close();
