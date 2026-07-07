"use client";

import { useEffect, useState } from "react";

type Option = { id: string; label: string; hex: string };

// Every option dresses the WHOLE page by driving --accent. "default" leaves the
// theme's own accent; "mono" is the umbrella treatment (accent collapses to ink).
const OPTIONS: Option[] = [
  { id: "default", label: "Default", hex: "var(--accent)" },
  { id: "mono", label: "Monochrome", hex: "var(--ink)" },
  { id: "digigraph", label: "DigiGraph", hex: "#e5b765" },
  { id: "digiquant", label: "DigiQuant", hex: "#3dd6c4" },
  { id: "digisearch", label: "DigiSearch", hex: "#5aa3c4" },
  { id: "digichat", label: "DigiChat", hex: "#e2708a" },
  { id: "digikey", label: "DigiKey", hex: "#d97a5a" },
  { id: "digivault", label: "DigiVault", hex: "#9d8fc9" },
  { id: "digistore", label: "DigiStore", hex: "#7b7fc7" },
  { id: "atlas", label: "Atlas", hex: "#6fbf94" },
  { id: "hermes", label: "Hermes", hex: "#4a8f7b" },
  { id: "kairos", label: "Kairos", hex: "#2f7a65" },
];

const LIVERY_CLASSES = OPTIONS.filter((o) => o.id !== "default" && o.id !== "mono").map(
  (o) => `accent-${o.id}`,
);

export function ThemeGallery() {
  const [active, setActive] = useState("default");

  // Apply the chosen livery to <body> so every component on the page re-dresses
  // live. Cleaned up on unmount so it only affects this page while open.
  useEffect(() => {
    const body = document.body;
    body.classList.remove(...LIVERY_CLASSES);
    body.style.removeProperty("--accent");
    if (active === "mono") body.style.setProperty("--accent", "var(--ink)");
    else if (active !== "default") body.classList.add(`accent-${active}`);
    return () => {
      body.classList.remove(...LIVERY_CLASSES);
      body.style.removeProperty("--accent");
    };
  }, [active]);

  return (
    <section className="section-block theme-gallery">
      <p className="kicker">{"// theme"}</p>
      <h2 className="title">Dress the whole reference.</h2>
      <p className="section-copy">
        Pick a livery and the entire page re-dresses — nav, links, charts, every accent — so you
        can read the system under any module&apos;s colour. Monochrome is the umbrella treatment
        (accent collapses to ink). Light and dark live in the top-bar toggle; the two compose.
      </p>

      <div className="tg-grid" role="radiogroup" aria-label="Page livery">
        {OPTIONS.map((o) => (
          <button
            key={o.id}
            type="button"
            role="radio"
            aria-checked={o.id === active}
            className={`tg-swatch${o.id === active ? " on" : ""}`}
            style={{ ["--tg" as string]: o.hex }}
            onClick={() => setActive(o.id)}
          >
            <span className="tg-chip" aria-hidden="true" />
            <span className="tg-label">{o.label}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
