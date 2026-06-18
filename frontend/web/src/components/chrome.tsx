"use client";
/** Shared nav, footer, and module card. Brand + links are passed in so both
 *  marketing apps reuse the same chrome. */
import { useState, type ReactNode } from "react";
import { ThemeToggle } from "./ThemeProvider";
import { Emblem } from "./emblems";
import { StackRow } from "./StackLogo";
import { type ModuleNode } from "../data/modules";

export interface NavLink { label: string; href: string; external?: boolean; cta?: boolean; }

export function Nav({ brand, links, mark }: { brand: ReactNode; links: NavLink[]; mark?: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <header className="site-nav">
      <div className="wrap nav-inner">
        <a className="brand" href="/" aria-label="home">{mark}{brand}</a>
        <nav className={`nav-links${open ? " open" : ""}`} aria-label="Primary">
          {links.map((l) => (
            <a key={l.href + l.label} href={l.href} className={l.cta ? "btn btn-sm" : undefined}
              target={l.external ? "_blank" : undefined} rel={l.external ? "noopener noreferrer" : undefined}
              onClick={() => setOpen(false)}>
              {l.label}{l.external && <span className="ext" aria-hidden="true"> ↗</span>}
            </a>
          ))}
        </nav>
        <div className="nav-tail">
          <ThemeToggle />
          <button className="nav-toggle" aria-label="Toggle navigation" aria-expanded={open}
            onClick={() => setOpen((v) => !v)}><span /><span /></button>
        </div>
      </div>
    </header>
  );
}

export function Footer({ links, meta }: { links: NavLink[]; meta: string }) {
  return (
    <footer className="footer">
      <div className="wrap footer-inner">
        <nav className="footer-links" aria-label="Footer">
          {links.map((l) => (
            <a key={l.href + l.label} href={l.href} target={l.external ? "_blank" : undefined}
              rel={l.external ? "noopener noreferrer" : undefined}>{l.label}</a>
          ))}
        </nav>
        <p className="footer-meta">{meta}</p>
      </div>
    </footer>
  );
}

export function ModuleCard({ m }: { m: ModuleNode }) {
  return (
    <a className={`mod-card t-${m.tier}`} href={`/modules/${m.id}`}>
      <div className="mod-card-top">
        <Emblem id={m.emblem} size={26} />
        <span className={`dg-tier t-${m.tier}`}>{m.tier}</span>
      </div>
      <h3>{m.name}</h3>
      <p className="role">{m.role}</p>
      <StackRow items={m.stack.slice(0, 4)} className="stack-row compact" />
    </a>
  );
}
