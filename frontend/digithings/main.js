/**
 * digithings.ai — landing wiring. Pulls behaviour from the shared foundation
 * (../design/site/*) and supplies page content: the typed terminal, the
 * capability teaser, and the connected-graph metadata.
 */
import { initTheme } from "../design/site/theme.js";
import { initNav, initCopy } from "../design/site/ui.js";
import { initReveal } from "../design/site/reveal.js";
import { typeTerminal } from "../design/site/terminal.js";
import { initGraph } from "../design/site/graph.js";

initTheme();
initNav();
initCopy();
initReveal();

/* hero terminal */
typeTerminal(document.getElementById("term-body"), [
  { kind: "cmd", text: "digithings --about" },
  { kind: "out", text: "open-core agentic stack · 10 modules · self-hosted" },
  { kind: "gap" },
  { kind: "cmd", text: "digithings install" },
  { kind: "install", text: "curl -fsSL https://digithings.ai/install.sh | sh", copy: true },
  { kind: "gap" },
  { kind: "cmd", text: "digithings modules --list" },
  { kind: "mod", name: "digigraph", text: "orchestration · langgraph supervisor" },
  { kind: "mod", name: "digiquant", text: "quant engine · nautilustrader" },
  { kind: "mod", name: "digisearch", text: "retrieval · multi-backend" },
  { kind: "mod", name: "digichat", text: "chat surface · byok" },
  { kind: "out", text: "+ digikey · digismith · digiclaw · digibase · digistore · digilink" },
]);
initCopy(); // re-wire any copy button rendered inside the terminal

/* connected graph */
const NAMES = {
  digigraph: "DigiGraph", digiquant: "DigiQuant", digisearch: "DigiSearch", digichat: "DigiChat",
  digikey: "DigiKey", digismith: "DigiSmith", digiclaw: "DigiClaw", digibase: "DigiBase",
  digistore: "DigiStore", digilink: "DigiLink",
};
const ROLES = {
  digigraph: "Orchestration supervisor — routes every request to the right specialist.",
  digiquant: "Quant engine — research, signals, and execution on NautilusTrader.",
  digisearch: "Retrieval — dense, sparse, and hybrid over any vector backend.",
  digichat: "Chat surface — BYOK every request; keys are never stored.",
  digikey: "Auth — RS256 JWTs and scoped API keys.",
  digismith: "Observability — spans, correlation IDs, PII redaction.",
  digiclaw: "Always-on runtime — scheduling and immutable audit.",
  digibase: "Shared HTTP and audit primitives for every module.",
  digistore: "Storage — S3, MinIO, Postgres, or SQLite behind one API.",
  digilink: "MCP protocol bridge for non-native transports.",
};
initGraph(".graph", { roles: ROLES, names: NAMES, defaultMod: "digigraph" });
// click a node → its detail page
document.querySelectorAll(".gnode").forEach((n) => {
  const go = () => { location.href = `modules.html?mod=${n.dataset.mod}`; };
  n.addEventListener("click", go);
  n.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
});

/* capability teaser */
const CAPS = {
  digigraph: { name: "DigiGraph", role: "One LangGraph supervisor inspects each request and routes it to the right specialist — quant, retrieval, or chat. Add a vertical via a declarative tool registry.", code: "POST /v1/workflow" },
  digiquant: { name: "DigiQuant", role: "Research → signals → execution on a NautilusTrader core. Every step audited; live trades stay human-gated.", code: 'register("strategy", cls, cfg)' },
  digisearch: { name: "DigiSearch", role: "Dense, sparse, and hybrid retrieval over Chroma, pgvector, Qdrant, or in-memory — one client, swap engines without touching code.", code: "DigiSearch().query(text, index)" },
  digichat: { name: "DigiChat", role: "Talk to your stack with your keys and your models. BYOK every request — keys forwarded, never stored.", code: "streamText({ model, messages })" },
};
const stage = document.getElementById("stage");
const pills = [...document.querySelectorAll("#pills .pill")];
function renderCap(k) {
  const d = CAPS[k];
  if (!stage || !d) return;
  const wrap = document.createElement("div");
  wrap.className = "swap";
  const h = document.createElement("h3"); h.textContent = d.name;
  const p = document.createElement("p"); p.textContent = d.role;
  const code = document.createElement("code"); code.className = "snippet"; code.textContent = d.code;
  const more = document.createElement("a"); more.className = "more"; more.href = `modules.html?mod=${k}`; more.textContent = `man ${k} →`;
  wrap.append(h, p, code, document.createElement("br"), more);
  stage.replaceChildren(wrap);
}
function selectCap(k) { pills.forEach((p) => p.setAttribute("aria-selected", String(p.dataset.k === k))); renderCap(k); }
pills.forEach((p) => p.addEventListener("click", () => { selectCap(p.dataset.k); stopRotate(); }));
renderCap("digigraph");

let rot;
const order = ["digigraph", "digiquant", "digisearch", "digichat"];
let ri = 0;
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
function startRotate() { if (!reduce) rot = setInterval(() => { ri = (ri + 1) % order.length; selectCap(order[ri]); }, 3800); }
function stopRotate() { clearInterval(rot); }
startRotate();
