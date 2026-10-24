import { chromium } from "playwright";
const b = await chromium.launch(); const p = await b.newPage();
await p.goto("file://" + new URL("./index.html", import.meta.url).pathname);
await p.waitForSelector('[data-slot="aui_work-chain-trigger"]');
await (await p.$('[data-slot="aui_work-chain-trigger"]')).click(); await p.waitForTimeout(300);
await (await p.$('[data-slot="tool-group-trigger"]')).click(); await p.waitForTimeout(300);
console.log(await p.evaluate(() => [...document.querySelectorAll('[data-slot="disclosure-chevron"]')].map(c => { const g=c.querySelector('[data-slot="dot-matrix-grid"]'); const s=getComputedStyle(g); return c.parentElement.getAttribute("data-slot")+" exp="+c.parentElement.getAttribute("aria-expanded")+" "+s.transitionProperty+" "+s.transitionDuration+" "+s.transform+" thread="+!!c.closest(".digichat-thread"); }).join("\n")));
await b.close();
