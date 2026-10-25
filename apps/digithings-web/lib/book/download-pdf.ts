import pages from "@/lib/book/generated/pages.json";

/**
 * The PDF is printed at build time by `scripts/book/print-pdf.mjs`; this only
 * fetches it.
 *
 * There used to be a renderer here — paginate the DOM, rasterise nineteen pages
 * through an SVG, slice them into a PDF. It took twenty-one seconds, because
 * the cost is the raster itself and no capture setting changes that, and it
 * could produce a black file when the page was not in a paint-ready state.
 * `/book` is a light, still page, so one printed edition is the whole story: the
 * download is a file.
 */
type Edition = { theme: string; palette: string; file: string };

function edition(): Edition | undefined {
  const list = (pages as { editions?: Edition[] }).editions ?? [];
  return list.find((entry) => entry.theme === "light" && entry.palette === "") ?? list[0];
}

export async function buildBookPdf(): Promise<{
  blob: Blob;
  filename: string;
  pages: number;
}> {
  const printed = edition();
  if (!printed) throw new Error("no printed edition in the build");
  const response = await fetch(`/book/${printed.file}`);
  if (!response.ok) throw new Error("the printed edition could not be read");
  return {
    blob: await response.blob(),
    filename: printed.file,
    pages: pages.pages,
  };
}

/** Warm the file while the pointer is on the button, so the click is a read. */
export function prefetchPrintedEdition(): void {
  const printed = edition();
  if (!printed) return;
  void fetch(`/book/${printed.file}`, { cache: "force-cache" }).catch(() => {});
}
