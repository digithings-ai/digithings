import type { MDXComponents } from "mdx/types";

import BookCode from "@/components/book/BookCode";
import BookFigure from "@/components/book/BookFigure";
import Reference from "@/components/book/Reference";

/**
 * The MDX component map (DIG-2821, U17).
 *
 * `@next/mdx` requires this file at the app root, and the book is the only
 * content in the app that goes through it. It maps the markdown primitives onto
 * the house long-form grammar: the mono voice for code, the ink scale for
 * headings, the prose measure and leading from `tokens.css`, and the hairline
 * rules the rest of the site uses.
 *
 * Two mappings are structural rather than cosmetic:
 *
 *  - `pre` becomes `BookCode`, the only place a code block gets its keyboard
 *    scroll container, overflow hint and copy control.
 *  - `table` gains a scroll wrapper, because a GFM table is as wide as its
 *    widest cell and the reading column is not.
 *
 * `img` is remapped rather than restyled. Every diagram in the book is a static
 * SVG under `/book/diagrams/`, which is what lets the web page and the printed
 * page load the same file, so `BookFigure` decides by that address and Next's
 * image optimiser never gets the chance to turn it into something else.
 */
export function useMDXComponents(components: MDXComponents): MDXComponents {
  return {
    h1: (props) => <h1 className="mt-[clamp(3rem,7vw,5rem)] mb-6 text-balance font-display text-[clamp(2rem,4vw,3rem)] leading-[1.05] tracking-[-0.02em]" {...props} />,
    h2: (props) => <h2 className="mt-12 mb-4 text-balance font-display text-[1.6rem] leading-[1.15] tracking-[-0.01em] text-ink" {...props} />,
    h3: (props) => <h3 className="mt-8 mb-3 text-balance font-display text-[1.2rem] leading-[1.25] text-ink" {...props} />,
    h4: (props) => <h4 className="mt-6 mb-2 font-mono text-[0.9rem] tracking-[0.02em] text-accent" {...props} />,
    p: (props) => <p className="mb-5 max-w-[var(--measure-prose)] text-[1.0625rem] leading-[var(--leading-prose)] text-ink-soft" {...props} />,
    ul: (props) => <ul className="mb-5 ml-5 max-w-[var(--measure-prose)] list-disc text-[1.0625rem] leading-[var(--leading-prose)] text-ink-soft" {...props} />,
    ol: (props) => <ol className="mb-5 ml-5 max-w-[var(--measure-prose)] list-decimal text-[1.0625rem] leading-[var(--leading-prose)] text-ink-soft" {...props} />,
    li: (props) => <li className="mb-1.5 pl-1" {...props} />,
    // A pull-quote in the book's voice: the hairline does the framing, not a
    // fill or a rounded card.
    blockquote: (props) => (
      <blockquote
        className="my-6 max-w-[var(--measure-prose)] border-l-2 border-hair-2 pl-5 text-[1.0625rem] leading-[var(--leading-prose)] text-ink-soft [&>p]:mb-3 [&>p:last-child]:mb-0"
        {...props}
      />
    ),
    hr: (props) => <hr className="my-10 border-hair border-t" {...props} />,
    code: (props) => <code className="font-mono text-[0.92em] text-ink" {...props} />,
    pre: (props) => <BookCode {...props} />,
    // Wide tables scroll inside their own box instead of widening the page.
    table: (props) => (
      <div className="book-table mb-6 max-w-full overflow-x-auto" tabIndex={0} role="region" aria-label="table">
        <table {...props} />
      </div>
    ),
    a: (props) => <a className="text-accent underline decoration-[color:var(--hair)] underline-offset-2 hover:decoration-[color:var(--ink-soft)]" {...props} />,
    // Routed through BookFigure, which decides by ADDRESS whether an image is a
    // book diagram (pan and zoom) or an ordinary picture (figure + caption).
    // Both are plain images underneath, so the PDF prints exactly what the page
    // shows.
    img: (props) => <BookFigure {...props} />,
    // "Go deeper" cards: the book keeps implementation detail in the reference
    // docs and links to it (DIG-2818 editorial rule).
    Reference,
    ...components,
  };
}
