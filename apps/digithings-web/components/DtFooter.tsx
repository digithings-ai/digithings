/**
 * DtFooter — one row of hairline boxes for the links that are not in the top
 * bar, then the full map in labeled columns (the gloom.sh footer shape).
 * The copyright and profile icons sit under the columns.
 */
import { FooterCells, SocialRow } from "@digithings/ui";
import { DT_FOOTER_BOXES, DT_FOOTER_META, DT_SITEMAP } from "@/app/_nav";

function Sitemap() {
  return (
    <div className="grid grid-cols-2 gap-x-[1.75rem] gap-y-10 px-[var(--page-pad)] py-[2.6rem] lg:grid-cols-5">
      {DT_SITEMAP.map((column) => (
        <nav key={column.label} aria-label={column.label} className="grid content-start gap-4">
          <p className="m-0 font-mono text-[0.75rem] tracking-[0.04em] text-ink-mute">
            [{column.label}]
          </p>
          <div className="grid gap-3">
            {column.links.map((link) => (
              <a
                key={link.href + link.label}
                href={link.href}
                target={link.external ? "_blank" : undefined}
                rel={link.external ? "noopener noreferrer" : undefined}
                className="w-fit font-mono text-[0.95rem] text-ink-soft underline decoration-transparent decoration-1 underline-offset-[0.3em] transition-[color,text-decoration-color] duration-150 hover:text-ink hover:decoration-ink-mute focus-visible:text-ink focus-visible:decoration-ink-mute"
              >
                {link.label}
              </a>
            ))}
          </div>
        </nav>
      ))}
    </div>
  );
}

export function DtFooter() {
  return (
    <FooterCells
      className="mt-[clamp(1.5rem,4vw,3rem)]"
      columns={4}
      cells={DT_FOOTER_BOXES}
      below={<Sitemap />}
      meta={DT_FOOTER_META}
      profiles={<SocialRow />}
    />
  );
}
