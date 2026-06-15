/**
 * graph.js — wires a connected platform graph authored in SVG.
 *
 * Expected markup inside a `.graph` container:
 *   <svg> with <line class="edge" data-a="<id>" data-b="<id>" .../>
 *   and <g class="gnode" data-mod="<id>" tabindex="0" role="button">…</g>
 *   plus an optional `.graph-readout` with `.readout-mod` and `.readout-role`.
 *
 * Behaviour: hovering/focusing a node dims the rest and highlights that node,
 * its edges, and their endpoints; the readout names the node + its role. Edges
 * draw in when the graph scrolls into view. Reduced-motion safe.
 *
 * opts: { roles: {id: roleText}, names: {id: displayName}, defaultMod: id }
 */
export function initGraph(root, opts = {}) {
  const graph = typeof root === "string" ? document.querySelector(root) : root;
  if (!graph) return;
  const svg = graph.querySelector("svg");
  if (!svg) return;

  const edges = [...svg.querySelectorAll(".edge")];
  const nodes = [...svg.querySelectorAll(".gnode")];
  const readoutMod = graph.querySelector(".readout-mod");
  const readoutRole = graph.querySelector(".readout-role");
  const roles = opts.roles || {};
  const names = opts.names || {};
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const defaultMod = opts.defaultMod || (nodes[0] && nodes[0].dataset.mod);

  const setReadout = (mod) => {
    if (readoutMod) readoutMod.textContent = names[mod] || mod;
    if (readoutRole) readoutRole.textContent = roles[mod] || "";
  };

  const activate = (mod) => {
    graph.classList.add("has-active");
    const near = new Set([mod]);
    edges.forEach((e) => {
      const hit = e.dataset.a === mod || e.dataset.b === mod;
      e.classList.toggle("is-active", hit);
      if (hit) { near.add(e.dataset.a); near.add(e.dataset.b); }
    });
    nodes.forEach((n) => n.classList.toggle("is-active", near.has(n.dataset.mod)));
    setReadout(mod);
  };
  const clear = () => {
    graph.classList.remove("has-active");
    edges.forEach((e) => e.classList.remove("is-active"));
    nodes.forEach((n) => n.classList.remove("is-active"));
    if (defaultMod) setReadout(defaultMod);
  };

  nodes.forEach((n) => {
    const mod = n.dataset.mod;
    n.addEventListener("mouseenter", () => activate(mod));
    n.addEventListener("focus", () => activate(mod));
    n.addEventListener("mouseleave", clear);
    n.addEventListener("blur", clear);
  });
  if (defaultMod) setReadout(defaultMod);

  if (!reduce && "IntersectionObserver" in window) {
    edges.forEach((e) => { try { e.style.setProperty("--len", e.getTotalLength()); } catch (_) {} });
    const io = new IntersectionObserver((entries, obs) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        edges.forEach((e, i) => { e.style.setProperty("--ed", (i * 0.06).toFixed(2) + "s"); e.classList.add("draw"); });
        obs.disconnect();
      });
    }, { threshold: 0.2 });
    io.observe(svg);
  }
}
