"use client";
import { useEffect, useState } from "react";
import { modules, type ModuleNode } from "@digithings/web";
import { writeHandoff } from "@/lib/chatHandoff";

/**
 * Terminal-manifest display of the ten DigiThings modules — a `digithings ps`
 * process list. Each row: a status dot (online vs roadmap), the lowercase
 * two-tone name (`digi` ink + suffix accent), the port, and the role.
 *
 * Clicking a row runs `digithings show <module>` and the module's description
 * (the prose that used to live on its own page) types out live at the cursor,
 * terminal-style — so the per-module pages fold into the manifest itself.
 * prefers-reduced-motion reveals the output instantly. Renders from the shared
 * `modules` data (single source of truth), sorted by graphOrder.
 */
function buildOutput(m: ModuleNode): string {
  const stack = m.stack.map((s) => s.name).join("  ·  ");
  return [m.tagline, "", ...m.summary, "", "stack   " + stack].join("\n");
}

/** Hand the selected module off to the full /chat page with a seeded question. */
function askAbout(m: ModuleNode): void {
  writeHandoff([], `What does ${m.id} do, and how do I use it?`);
  window.location.href = "/chat";
}

export function ModuleManifest() {
  const rows = [...modules].sort((a, b) => a.graphOrder - b.graphOrder);
  const online = rows.filter((m) => m.tier !== "roadmap").length;
  const road = rows.length - online;

  const [sel, setSel] = useState<string | null>(null);
  const [shown, setShown] = useState(0);
  const selMod = sel ? rows.find((m) => m.id === sel) ?? null : null;
  const out = selMod ? buildOutput(selMod) : "";

  // The summary types out character-by-character: this effect resets and then drives
  // `shown` as an animation, so synchronous setState in the effect body is intentional.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!selMod) {
      setShown(0);
      return;
    }
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setShown(out.length);
      return;
    }
    setShown(0);
    let i = 0;
    const stepN = Math.max(2, Math.ceil(out.length / 90)); // ~1.5s regardless of length
    const id = window.setInterval(() => {
      i += stepN;
      if (i >= out.length) {
        i = out.length;
        window.clearInterval(id);
      }
      setShown(i);
    }, 16);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sel]);
  /* eslint-enable react-hooks/set-state-in-effect */

  return (
    <div className="dt-manifest" aria-label="digithings module manifest">
      <div className="dt-manifest-head">
        <span className="dt-mh-prompt">$</span> digithings ps
        <span className="dt-mh-meta"> · {online} online · {road} on the roadmap</span>
      </div>
      <div className="dt-manifest-body">
      <ol className="dt-manifest-rows">
        {rows.map((m, i) => {
          const isRoad = m.tier === "roadmap";
          const suffix = m.id.replace(/^digi/, "");
          const isSel = sel === m.id;
          return (
            <li
              key={m.id}
              className={`dt-mrow${isRoad ? " is-road" : ""}${isSel ? " is-sel" : ""}`}
              style={{ animationDelay: `${i * 55}ms` }}
            >
              <button
                type="button"
                className="dt-mrow-link"
                aria-expanded={isSel}
                onClick={() => setSel(isSel ? null : m.id)}
              >
                <span className={`dt-dot${isRoad ? " off" : ""}`} aria-hidden="true" />
                <span className="dt-mname">
                  <span className="dt-d">digi</span>
                  <span className="dt-s">{suffix}</span>
                </span>
                <span className="dt-mport">{m.port ? `:${m.port}` : isRoad ? "roadmap" : "—"}</span>
                <span className="dt-mrole">{m.role}</span>
              </button>
            </li>
          );
        })}
      </ol>
      <div className="dt-out">
        <div className="dt-out-show" aria-live="polite">
          {selMod ? (
            <>
              <div className="dt-out-cmd">
                <span className="dt-mh-prompt">$</span> digithings show{" "}
                <span className="dt-d">digi</span>
                <span className="dt-s">{selMod.id.replace(/^digi/, "")}</span>
              </div>
              <pre className="dt-out-body">
                {out.slice(0, shown)}
                <span className="dt-cur" />
              </pre>
              <button type="button" className="dt-ask" onClick={() => askAbout(selMod)}>
                ask <span className="dt-d">digi</span>
                <span className="dt-s">chat</span> about{" "}
                <span className="dt-d">digi</span>
                <span className="dt-s">{selMod.id.replace(/^digi/, "")}</span> →
              </button>
            </>
          ) : (
            <div className="dt-out-cmd">
              <span className="dt-mh-prompt">$</span>{" "}
              <span className="dt-out-dim">select a module to inspect</span>
              <span className="dt-cur" />
            </div>
          )}
        </div>
      </div>
      </div>
    </div>
  );
}
