"use client";

/**
 * The book's export bar: one boxed button per format, beside the contents.
 *
 * It replaces a single text link that said "download the pdf". The reader
 * should be able to see what they can take away without hovering anything, so
 * each format is a cell carrying its own mark and name.
 *
 * Every button builds its file in the browser from the reader's own copy of the
 * book, in the reader's own theme:
 *
 *  - **PDF** — `buildBookPdf`, the same builder the chapter pages use, so the
 *    download is the printed edition with this palette's diagrams and field;
 *  - **HTML** — the paginated page boxes flattened into one self-contained
 *    file (`lib/book/export-html`);
 *  - **DOCX** — a real OOXML package of the book's text and figures
 *
 * The file name is on each button, because three downloads from one page
 * should not arrive as three files the reader has to open to tell apart.
 */
import { useEffect, useState } from "react";

import { buildBookPdf, prefetchPrintedEdition } from "@/lib/book/download-pdf";
import { bookFilename, saveBlob } from "@/lib/book/export-file";
import { buildBookHtml } from "@/lib/book/export-html";

type Format = "pdf" | "html";
type State = "idle" | "working" | "done" | "error";

/**
 * The formats, in the order they are offered. PDF leads: it is the one that
 * looks like the book.
 */
export const BOOK_EXPORT_FORMATS = [
  { id: "pdf", label: "PDF", extension: "pdf" },
  { id: "html", label: "HTML", extension: "html" },
] as const satisfies ReadonlyArray<{ id: Format; label: string; extension: string }>;

/** Line marks rather than a logo per vendor: the format, drawn simply. */
function FormatMark({ format }: { format: Format }) {
  const common = {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.4,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };
  if (format === "pdf") {
    return (
      <svg {...common}>
        <path d="M6 2.75h7.5L18 7.25V21.25H6z" />
        <path d="M13.5 2.75v4.5H18" />
        <path d="M9 16.5v-3h1.6a1.5 1.5 0 0 1 0 3H9" />
        <path d="M14 16.5v-3h1.1a1.5 1.5 0 0 1 0 3H14" />
      </svg>
    );
  }
  if (format === "html") {
    return (
      <svg {...common}>
        <path d="M9 7.5 4.5 12 9 16.5" />
        <path d="M15 7.5 19.5 12 15 16.5" />
        <path d="M13.5 5.5l-3 13" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <path d="M6 2.75h12V21.25H6z" />
      <path d="M9 8h6" />
      <path d="M9 12h6" />
      <path d="M9 16h3.5" />
    </svg>
  );
}

const staticNames: Record<Format, string> = {
  pdf: "the-digithings-book.pdf",
  html: "the-digithings-book.html",
};

export default function BookExportBar() {
  const [state, setState] = useState<Record<Format, State>>({ pdf: "idle", html: "idle" });
  const [names, setNames] = useState<Record<Format, string>>(staticNames);

  // The name says which theme and palette the file was built in. It is read
  // after mount, because the theme lives on <html> and not in this render.
  useEffect(() => {
    const sync = () =>
      setNames({
        pdf: bookFilename("pdf"),
        html: bookFilename("html"),
      });
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme", "data-palette"],
    });
    return () => observer.disconnect();
  }, []);

  async function build(format: Format): Promise<{ blob: Blob; filename: string }> {
    if (format === "pdf") {
      const { blob, filename } = await buildBookPdf();
      return { blob, filename };
    }
    if (format === "html") {
      const { blob, filename } = await buildBookHtml();
      return { blob, filename };
    }
    throw new Error(`no builder for ${format}`);
  }

  // The cell itself carries the progress: it says "working" and comes back when
  // the file is written. A line of prose under the buttons was noise.
  async function run(format: Format) {
    if (state[format] === "working") return;
    setState((current) => ({ ...current, [format]: "working" }));
    try {
      const { blob, filename } = await build(format);
      saveBlob(blob, filename);
      setState((current) => ({ ...current, [format]: "done" }));
    } catch (error) {
      console.error(`book: could not build the ${format}`, error);
      setState((current) => ({ ...current, [format]: "error" }));
    }
  }

  return (
    <div className="book-export" role="group" aria-label="export the book">
      <div className="book-export__row">
        {BOOK_EXPORT_FORMATS.map((format) => {
          const working = state[format.id] === "working";
          return (
            <button
              key={format.id}
              type="button"
              className="book-export__btn"
              data-format={format.id}
              data-state={state[format.id]}
              title={`download ${names[format.id]}`}
              aria-label={`download the book as ${format.label} — ${names[format.id]}`}
              aria-busy={working}
              disabled={working}
              onPointerEnter={format.id === "pdf" ? prefetchPrintedEdition : undefined}
              onFocus={format.id === "pdf" ? prefetchPrintedEdition : undefined}
              onClick={() => void run(format.id)}
            >
              <span className="book-export__mark" aria-hidden>
                <FormatMark format={format.id} />
              </span>
              <span className="book-export__label">{format.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
