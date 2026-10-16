import type { MDXComponents } from "mdx/types";

import BookFigure from "@/components/book/BookFigure";
import Reference from "@/components/book/Reference";

/**
 * The MDX component map (DIG-2821).
 *
 * `@next/mdx` requires this file at the app root. It maps the markdown
 * primitives onto the house long-form grammar: the mono voice for code, the
 * ink scale for headings, and the hairline rules the rest of the site uses.
 *
 * `img` is remapped rather than restyled. Every diagram in the book is a static
 * SVG under `/book/diagrams/`, which is what lets the web page and the printed
 * page load the same file — so `BookFigure` decides by that address, and Next's
 * image optimiser never gets the chance to turn it into something else.
 */
export function useMDXComponents(components: MDXComponents): MDXComponents {
  return {
    h1: (props) => <h1 className="mt-[clamp(3rem,7vw,5rem)] mb-6 font-display text-[clamp(2rem,4vw,3rem)] leading-[1.05] tracking-[-0.02em]" {...props} />,
    h2: (props) => <h2 className="mt-12 mb-4 font-display text-[1.6rem] leading-[1.15] tracking-[-0.01em] text-ink" {...props} />,
    h3: (props) => <h3 className="mt-8 mb-3 font-display text-[1.2rem] leading-[1.25] text-ink" {...props} />,
    h4: (props) => <h4 className="mt-6 mb-2 font-mono text-[0.9rem] tracking-[0.02em] text-accent" {...props} />,
    p: (props) => <p className="mb-4 max-w-[64ch] text-[1.05rem] leading-[1.7] text-ink-soft" {...props} />,
    ul: (props) => <ul className="mb-4 ml-5 list-disc text-[1.05rem] leading-[1.7] text-ink-soft" {...props} />,
    ol: (props) => <ol className="mb-4 ml-5 list-decimal text-[1.05rem] leading-[1.7] text-ink-soft" {...props} />,
    code: (props) => <code className="font-mono text-[0.92em] text-ink" {...props} />,
    pre: (props) => <pre className="mb-6 overflow-x-auto border-hair border p-4 font-mono text-[0.85rem] leading-[1.3] text-ink" {...props} />,
    a: (props) => <a className="text-accent underline decoration-[color:var(--hair)] underline-offset-2" {...props} />,
    // Routed through BookFigure, which decides by ADDRESS whether an image is a
    // book diagram (pan and zoom) or an ordinary picture (left alone). Both are
    // plain images underneath — the interaction is an addition, not a
    // replacement, so the PDF prints exactly what the page shows.
    img: (props) => <BookFigure {...props} />,
    // "Go deeper" cards: the book keeps implementation detail in the reference
    // docs and links to it (DIG-2818 editorial rule).
    Reference,
    ...components,
  };
}
