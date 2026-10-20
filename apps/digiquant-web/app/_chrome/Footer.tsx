import { FooterWordmark } from "./FooterWordmark";
import { DQ_FOOTER_META, DQ_SITEMAP } from "../_nav";

const RAIL_BOX = "mx-auto w-full max-w-[calc(var(--frame-w)+2*var(--page-pad))]";
const LINK =
  "w-fit text-[0.9rem] text-ink-soft underline decoration-transparent decoration-1 underline-offset-[0.3em] transition-[color,text-decoration-color] duration-150 hover:text-ink hover:decoration-ink-mute focus-visible:text-ink focus-visible:decoration-ink-mute";

/** Closing chrome, built on the same rails as every band: the pixel wordmark, then the
 *  sitemap in labelled columns, then one line of meta. Nothing here runs outside the
 *  rail box, so the links start on the wordmark's left edge. */
export function Footer() {
  return (
    <footer className="relative z-10 border-t border-hair">
      <FooterWordmark />
      <div className={RAIL_BOX}>
        <div className="grid grid-cols-2 gap-x-[1.75rem] gap-y-10 border-t border-hair px-[var(--page-pad)] py-[2.6rem] md:grid-cols-3 lg:grid-cols-5">
          {DQ_SITEMAP.map((column) => (
            <nav key={column.label} aria-label={column.label} className="grid content-start gap-4">
              <p className="m-0 font-mono text-[0.75rem] tracking-[0.04em] text-ink-mute">[{column.label}]</p>
              <div className="grid gap-3">
                {column.links.map((link) => (
                  <a
                    key={link.href + link.label}
                    href={link.href}
                    target={link.external ? "_blank" : undefined}
                    rel={link.external ? "noopener noreferrer" : undefined}
                    className={LINK}
                  >
                    {link.label}
                  </a>
                ))}
              </div>
            </nav>
          ))}
        </div>
        <div className="border-t border-hair px-[var(--page-pad)] py-[1.25rem] font-mono text-[0.75rem] tracking-[0.02em] text-ink-mute">
          {DQ_FOOTER_META}
        </div>
      </div>
    </footer>
  );
}
