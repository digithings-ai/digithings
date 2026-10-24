import { chromium } from "playwright";
const BASE = process.argv[2];
const D = process.argv[3];
if (!BASE || !D) { console.error("usage: shot.mjs <base> <outdir>"); process.exit(2); }
const b = await chromium.launch({ channel: "chrome" });
const p = await b.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
const targets = [
  ["digiquant-io-home", "/", false],
  ["digiquant-io-home-full", "/", true],
  ["app-brief-desk", "/app/", false],
  ["app-terminal", "/app/tools/terminal/", false],
];
const report = [];
for (const [name, path, full] of targets) {
  let httpStatus = null, navError = null;
  try {
    const resp = await p.goto(BASE + path, { waitUntil: "domcontentloaded", timeout: 45000 });
    httpStatus = resp ? resp.status() : null;
  } catch (e) { navError = String(e).split("\n")[0]; }
  await p.waitForTimeout(5000);
  let text = "";
  try { text = (await p.evaluate(() => document.body ? document.body.innerText : "")) || ""; } catch {}
  const errMarkers = ["Application error", "Build Error", "This page could not be found",
                      "Live data is temporarily unavailable", "unhandled runtime error"]
    .filter(m => text.includes(m));
  await p.screenshot({ path: `${D}/${name}.png`, fullPage: full });
  const bytes = (await import("node:fs")).statSync(`${D}/${name}.png`).size;
  report.push({ name, path, httpStatus, navError, pngBytes: bytes,
                finalUrl: p.url(), bodyChars: text.length,
                firstLine: text.split("\n").find(s => s.trim()) || "",
                errMarkers });
  console.log(JSON.stringify(report[report.length - 1]));
}
await b.close();
