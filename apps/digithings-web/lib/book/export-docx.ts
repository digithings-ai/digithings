"use client";

/**
 * A real `.docx` (OOXML) of the book, built in the browser.
 *
 * The source is the book as it is on screen: the page boxes the reader is
 * already looking at. Their text is in reading order, so the Word file is the
 * same words in a reflowable document — a Word file is not a page-for-page
 * copy of a printed page, and pretending otherwise would produce a worse
 * document, not a more faithful one.
 *
 * Two details of the paginated DOM matter here:
 *
 *  - a paragraph that spans a page break is cloned into a fragment per page,
 *    with `data-split-from` on the continuation. Those fragments are joined
 *    back into one paragraph, or the export reads as sentences that stop and
 *    restart at every page.
 *  - pagedjs keeps measurement copies of some blocks (`data-undisplayed`).
 *    They are not content and would duplicate the contents page.
 *
 * Figures are the rendered PNGs already in the page (`blob:` sources), so the
 * diagrams travel with the document instead of leaving holes in it.
 *
 * The package is hand-built: no dependency in the app writes OOXML, and the
 * parts are small and fixed — content types, relationships, styles, media and
 * one document. `zip.ts` is the container.
 */
import { storedZip, type ZipEntry } from "./zip";
import { bookFilename } from "./export-file";

/** Word measures everything in twentieths of a point. */
const TWIPS_PER_INCH = 1440;
/** A4, and the book's print margins — the same frame the printed page uses. */
const PAGE_WIDTH = Math.round(8.268 * TWIPS_PER_INCH);
const PAGE_HEIGHT = Math.round(11.693 * TWIPS_PER_INCH);
const MARGIN = Math.round(0.7874 * TWIPS_PER_INCH);

/** EMU, for drawing extents. */
const EMU_PER_INCH = 914400;
/** Text column width inside the A4 margins — the widest a figure can be. */
const COLUMN_INCHES = (PAGE_WIDTH - 2 * MARGIN) / TWIPS_PER_INCH;
const FIGURE_MAX_INCHES = COLUMN_INCHES;
const FIGURE_MAX_HEIGHT_INCHES = 4.6;

/** Every block-level thing the book can put on a page. */
const BLOCK_SELECTOR = "h1,h2,h3,h4,h5,h6,p,li,pre,figcaption,blockquote,tr,img";

/** Inline elements that keep the flow of the sentence they sit in. */
const INLINE_STYLE_TAGS = new Set(["STRONG", "B", "EM", "I", "CODE", "A", "CITE", "SMALL", "SUP", "SUB", "MARK", "U", "S"]);

export type Run = { text: string; bold?: boolean; italic?: boolean; mono?: boolean };
/** One table cell's text. */
export type Cell = Run[];
/** One table row: its cells. */
export type TableRow = Cell[];

export type DocBlock =
  | { kind: "heading"; level: 1 | 2 | 3; runs: Run[] }
  | { kind: "paragraph"; runs: Run[] }
  | { kind: "bullet"; runs: Run[] }
  | { kind: "quote"; runs: Run[] }
  | { kind: "code"; runs: Run[] }
  | { kind: "caption"; runs: Run[] }
  | { kind: "table"; rows: TableRow[] }
  | { kind: "figure"; data: Uint8Array; width: number; height: number; alt: string };

function escapeXml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    // Control characters are illegal in XML 1.0 and make Word refuse the file.
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, "");
}

/**
 * Flatten an element into styled runs.
 *
 * A structural child (`span`, `div`) is separated from what precedes it by a
 * space: the contents rows are spans, and without the separator a chapter and
 * its page number run together as "Why this book exists3".
 */
function runsOf(node: Node, style: Omit<Run, "text"> = {}, out: Run[] = []): Run[] {
  for (const child of Array.from(node.childNodes)) {
    if (child.nodeType === 3) {
      const text = (child.textContent ?? "").replace(/\s+/g, " ");
      if (text) out.push({ ...style, text });
      continue;
    }
    if (child.nodeType !== 1) continue;
    const element = child as Element;
    const tag = element.tagName;
    if (tag === "SCRIPT" || tag === "STYLE" || tag === "SVG") continue;
    // A block can hide part of itself: each contents row carries the chapter's
    // summary in a paragraph the book hides on paper, and carrying that into
    // Word would turn the contents into twelve sentences of blurb.
    if (!isVisible(element)) continue;
    const next = { ...style };
    if (tag === "STRONG" || tag === "B") next.bold = true;
    if (tag === "EM" || tag === "I" || tag === "CITE") next.italic = true;
    if (tag === "CODE") next.mono = true;
    if (!INLINE_STYLE_TAGS.has(tag)) {
      const previous = out[out.length - 1];
      if (previous && !/\s$/.test(previous.text) && (element.textContent ?? "").trim()) {
        out.push({ ...style, text: " " });
      }
    }
    runsOf(element, next, out);
  }
  return out;
}

/** One line of prose, without the leading/trailing whitespace runs. */
function textRuns(node: Element): Run[] {
  const runs = runsOf(node)
    .map((run) => ({ ...run, text: run.text.replace(/\s+/g, " ") }))
    .filter((run) => run.text.length > 0);
  // Collapse the doubled spaces that inline boundaries can leave behind.
  const joined: Run[] = [];
  for (const run of runs) {
    const previous = joined[joined.length - 1];
    if (previous && /\s$/.test(previous.text) && /^\s/.test(run.text)) {
      joined.push({ ...run, text: run.text.replace(/^\s+/, "") });
      continue;
    }
    joined.push(run);
  }
  const first = joined[0];
  if (first) first.text = first.text.replace(/^\s+/, "");
  const last = joined[joined.length - 1];
  if (last) last.text = last.text.replace(/\s+$/, "");
  return joined.filter((run) => run.text.length > 0);
}

function textOf(runs: readonly Run[]): string {
  return runs.map((run) => run.text).join("");
}

function headingLevel(tag: string): 1 | 2 | 3 {
  const depth = Number(tag.slice(1));
  if (depth <= 2) return 1;
  if (depth === 3) return 2;
  return 3;
}

/** Chromium and WebKit both expose this; happy-dom does not, and neither does
 *  every future engine, so absence means "assume visible". */
function isVisible(node: Element): boolean {
  const check = (node as Element & { checkVisibility?: () => boolean }).checkVisibility;
  return typeof check === "function" ? check.call(node) : true;
}

type Raster = { data: Uint8Array; width: number; height: number };

/** How wide a figure is captured, before it is scaled into the page's column. */
const RASTER_MAX_PIXELS = 1600;

/**
 * The figure as PNG bytes.
 *
 * The book's diagrams are SVG — `<img>` elements over `blob:` URLs, one light
 * and one dark per figure — and a Word package cannot reference an SVG the same
 * way it references a bitmap, and `image/svg+xml` written into `word/media` as
 * `.png` is a file that opens as a blank box. So the drawing is rasterized on a
 * canvas at the reader's own paper colour, which is also what makes a dark
 * palette's diagrams legible on Word's white page instead of invisible.
 */
async function figureRaster(image: HTMLImageElement, source: string): Promise<Raster | null> {
  const response = await fetch(source);
  if (!response.ok) return null;
  const type = response.headers.get("content-type") ?? "";
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (bytes.length === 0) return null;

  const raster = (data: Uint8Array) => ({
    data,
    width: image.naturalWidth || image.width || 0,
    height: image.naturalHeight || image.height || 0,
  });
  if (type.includes("png")) return raster(bytes);
  if (type.includes("jpeg") || type.includes("jpg")) return raster(bytes);
  if (!type.includes("svg")) return raster(bytes);

  const url = URL.createObjectURL(new Blob([bytes], { type: "image/svg+xml" }));
  try {
    const drawing = new Image();
    await new Promise<void>((resolve, reject) => {
      drawing.onload = () => resolve();
      drawing.onerror = () => reject(new Error("the diagram could not be drawn"));
      drawing.src = url;
    });
    const natural = Math.max(1, drawing.naturalWidth);
    const scale = Math.min(2, RASTER_MAX_PIXELS / natural);
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(natural * scale));
    canvas.height = Math.max(1, Math.round((drawing.naturalHeight || natural) * scale));
    const context = canvas.getContext("2d");
    if (!context) return null;
    const paper = getComputedStyle(document.documentElement).getPropertyValue("--bg").trim();
    if (paper) {
      context.fillStyle = paper;
      context.fillRect(0, 0, canvas.width, canvas.height);
    }
    context.drawImage(drawing, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob((value) => resolve(value), "image/png"),
    );
    if (!blob) return null;
    return {
      data: new Uint8Array(await blob.arrayBuffer()),
      width: canvas.width,
      height: canvas.height,
    };
  } finally {
    URL.revokeObjectURL(url);
  }
}

async function figureOf(image: HTMLImageElement): Promise<DocBlock | null> {
  // The light and dark diagram drawings both live in the page; the one the
  // theme hides is not part of what the reader is reading.
  if (!isVisible(image)) return null;
  const source = image.getAttribute("src") ?? "";
  if (!source) return null;
  try {
    const raster = await figureRaster(image, source);
    if (!raster || raster.width <= 0 || raster.height <= 0) return null;

    const ratio = raster.height / raster.width;
    let width = FIGURE_MAX_INCHES;
    let height = width * ratio;
    if (height > FIGURE_MAX_HEIGHT_INCHES) {
      height = FIGURE_MAX_HEIGHT_INCHES;
      width = height / ratio;
    }
    return {
      kind: "figure",
      data: raster.data,
      width: Math.round(width * EMU_PER_INCH),
      height: Math.round(height * EMU_PER_INCH),
      alt: image.getAttribute("alt") ?? "",
    };
  } catch (error) {
    console.error("book: could not include a figure in the docx", error);
    return null;
  }
}

/**
 * The book's blocks, in reading order, from the paginated page boxes.
 *
 * Only the outermost match on each branch is emitted, so a list item is one
 * bullet rather than a bullet plus the paragraphs inside it. A block that
 * continues a split carries `data-split-from`, and its text is appended to the
 * paragraph before it instead of starting a new one.
 */
export async function collectBlocks(root: ParentNode): Promise<DocBlock[]> {
  const blocks: DocBlock[] = [];
  const contents = Array.from(root.querySelectorAll(".pagedjs_page .pagedjs_page_content"));
  if (contents.length === 0) throw new Error("the book has not paginated yet");

  for (const content of contents) {
    const nodes = Array.from(content.querySelectorAll(BLOCK_SELECTOR)).filter((node) => {
      // Hidden copies pagedjs keeps for measurement (the contents' summary
      // lines, a diagram variant the theme switches off) are not content.
      if (!isVisible(node)) return false;
      const parent = node.parentElement?.closest(BLOCK_SELECTOR);
      return !parent;
    });

    for (const node of nodes) {
      const tag = node.tagName;
      if (tag === "IMG") {
        const figure = await figureOf(node as HTMLImageElement);
        if (figure) blocks.push(figure);
        continue;
      }

      if (tag === "TR") {
        const cells = Array.from(node.querySelectorAll("th,td")).map((cell) => textRuns(cell));
        const previous = blocks[blocks.length - 1];
        // A table that runs over a page break arrives as two sets of rows; the
        // reader is reading one table, so the export keeps one.
        if (previous?.kind === "table") {
          previous.rows.push(cells);
        } else {
          blocks.push({ kind: "table", rows: [cells] });
        }
        continue;
      }

      const runs = textRuns(node);
      if (textOf(runs).trim().length === 0) continue;

      if (node.hasAttribute("data-split-from")) {
        const previous = blocks[blocks.length - 1];
        if (previous && "runs" in previous) {
          previous.runs = [...previous.runs, { text: " " }, ...runs];
          continue;
        }
      }

      if (tag === "H1" || tag === "H2" || tag === "H3" || tag === "H4" || tag === "H5" || tag === "H6") {
        blocks.push({ kind: "heading", level: headingLevel(tag), runs });
      } else if (tag === "LI") {
        blocks.push({ kind: "bullet", runs });
      } else if (tag === "BLOCKQUOTE") {
        blocks.push({ kind: "quote", runs });
      } else if (tag === "PRE") {
        blocks.push({ kind: "code", runs });
      } else if (tag === "FIGCAPTION") {
        blocks.push({ kind: "caption", runs });
      } else {
        blocks.push({ kind: "paragraph", runs });
      }
    }
  }

  return blocks;
}

function runXml(run: Run): string {
  const properties = [
    run.bold ? "<w:b/>" : "",
    run.italic ? "<w:i/>" : "",
    run.mono ? '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/>' : "",
  ].join("");
  const text = escapeXml(run.text);
  return `<w:r>${properties ? `<w:rPr>${properties}</w:rPr>` : ""}<w:t xml:space="preserve">${text}</w:t></w:r>`;
}

function paragraphXml(style: string, runs: readonly Run[], extra = ""): string {
  return `<w:p><w:pPr><w:pStyle w:val="${style}"/>${extra}</w:pPr>${runs.map(runXml).join("")}</w:p>`;
}

function tableXml(rows: readonly TableRow[]): string {
  const columns = Math.max(1, ...rows.map((row) => row.length));
  const width = Math.floor((PAGE_WIDTH - 2 * MARGIN) / columns);
  const border = (side: string) =>
    `<w:${side} w:val="single" w:sz="4" w:space="0" w:color="auto"/>`;
  const cells = rows
    .map(
      (row) =>
        `<w:tr>${row
          .map(
            (cell) =>
              `<w:tc><w:tcPr><w:tcW w:w="${width}" w:type="dxa"/></w:tcPr>${paragraphXml("TableText", cell)}</w:tc>`,
          )
          .join("")}</w:tr>`,
    )
    .join("");
  return (
    `<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/><w:tblBorders>` +
    border("top") +
    border("left") +
    border("bottom") +
    border("right") +
    border("insideH") +
    border("insideV") +
    `</w:tblBorders></w:tblPr>` +
    `<w:tblGrid>${Array.from({ length: columns }, () => `<w:gridCol w:w="${width}"/>`).join("")}</w:tblGrid>` +
    `${cells}</w:tbl>`
  );
}

function figureXml(figure: Extract<DocBlock, { kind: "figure" }>, id: number, relationship: string): string {
  const description = escapeXml(figure.alt || `figure ${id}`);
  return (
    `<w:p><w:pPr><w:pStyle w:val="Figure"/><w:jc w:val="center"/></w:pPr><w:r><w:drawing>` +
    `<wp:inline distT="0" distB="0" distL="0" distR="0">` +
    `<wp:extent cx="${figure.width}" cy="${figure.height}"/>` +
    `<wp:docPr id="${id}" name="Figure ${id}" descr="${description}"/>` +
    `<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">` +
    `<pic:pic><pic:nvPicPr><pic:cNvPr id="${id}" name="figure-${id}.png"/><pic:cNvPicPr/></pic:nvPicPr>` +
    `<pic:blipFill><a:blip r:embed="${relationship}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>` +
    `<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="${figure.width}" cy="${figure.height}"/></a:xfrm>` +
    `<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>` +
    `</a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>`
  );
}

const STYLES_XML = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault><w:rPr><w:rFonts w:ascii="Georgia" w:hAnsi="Georgia"/><w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr></w:rPrDefault>
    <w:pPrDefault><w:pPr><w:spacing w:after="140" w:line="288" w:lineRule="auto"/></w:pPr></w:pPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="480" w:after="160"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:sz w:val="40"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="360" w:after="120"/><w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:b/><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:sz w:val="30"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="280" w:after="100"/><w:outlineLvl w:val="2"/></w:pPr><w:rPr><w:b/><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:sz w:val="24"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/><w:pPr><w:ind w:left="425" w:hanging="284"/></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="Quote"><w:name w:val="Quote"/><w:basedOn w:val="Normal"/><w:pPr><w:ind w:left="425"/><w:spacing w:before="120" w:after="160"/></w:pPr><w:rPr><w:i/><w:color w:val="595959"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Code"><w:name w:val="Code"/><w:basedOn w:val="Normal"/><w:pPr><w:shd w:val="clear" w:fill="F2F2F2"/><w:ind w:left="170"/></w:pPr><w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/><w:sz w:val="19"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Caption"><w:name w:val="caption"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="60" w:after="240"/></w:pPr><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:sz w:val="18"/><w:color w:val="595959"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Figure"><w:name w:val="Figure"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="60"/></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="TableText"><w:name w:val="Table Text"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="40" w:after="40"/></w:pPr><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:sz w:val="18"/></w:rPr></w:style>
</w:styles>`;

function documentXml(blocks: readonly DocBlock[]): string {
  let mediaIndex = 0;
  const body = blocks
    .map((block) => {
      switch (block.kind) {
        case "heading":
          return paragraphXml(`Heading${block.level}`, block.runs);
        case "bullet":
          return paragraphXml("ListParagraph", [{ text: "\u2022\u00a0" }, ...block.runs]);
        case "quote":
          return paragraphXml("Quote", block.runs);
        case "code":
          return paragraphXml("Code", block.runs);
        case "caption":
          return paragraphXml("Caption", block.runs);
        case "table":
          return tableXml(block.rows);
        case "figure": {
          mediaIndex += 1;
          return figureXml(block, mediaIndex, `rId${mediaIndex + 1}`);
        }
        case "paragraph":
        default:
          return paragraphXml("Normal", block.runs);
      }
    })
    .join("");

  return (
    `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
    `<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"` +
    ` xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"` +
    ` xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"` +
    ` xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"` +
    ` xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">` +
    `<w:body>${body}` +
    `<w:sectPr><w:pgSz w:w="${PAGE_WIDTH}" w:h="${PAGE_HEIGHT}"/>` +
    `<w:pgMar w:top="${MARGIN}" w:right="${MARGIN}" w:bottom="${MARGIN}" w:left="${MARGIN}" w:header="709" w:footer="709" w:gutter="0"/>` +
    `</w:sectPr></w:body></w:document>`
  );
}

const CONTENT_TYPES = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>`;

const ROOT_RELS = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>`;

function documentRels(mediaCount: number): string {
  const images = Array.from(
    { length: mediaCount },
    (_, index) =>
      `<Relationship Id="rId${index + 2}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/figure-${index + 1}.png"/>`,
  ).join("");
  return (
    `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
    `<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">` +
    `<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>` +
    `${images}</Relationships>`
  );
}

/** The `.docx` package, as bytes. Exposed so a test can read the parts. */
export function docxBytes(blocks: readonly DocBlock[]): Uint8Array {
  const figures = blocks.filter((block): block is Extract<DocBlock, { kind: "figure" }> => block.kind === "figure");
  const entries: ZipEntry[] = [
    { name: "[Content_Types].xml", data: new TextEncoder().encode(CONTENT_TYPES) },
    { name: "_rels/.rels", data: new TextEncoder().encode(ROOT_RELS) },
    { name: "word/document.xml", data: new TextEncoder().encode(documentXml(blocks)) },
    { name: "word/styles.xml", data: new TextEncoder().encode(STYLES_XML) },
    { name: "word/_rels/document.xml.rels", data: new TextEncoder().encode(documentRels(figures.length)) },
    ...figures.map((figure, index) => ({
      name: `word/media/figure-${index + 1}.png`,
      data: figure.data,
    })),
  ];
  return storedZip(entries);
}

/** Where the file goes: the theme is in the name, because the file carries it. */
export async function buildBookDocx(): Promise<{ blob: Blob; filename: string; blocks: number }> {
  const blocks = await collectBlocks(document);
  if (blocks.length === 0) throw new Error("the book has no text to export");
  const bytes = docxBytes(blocks);
  return {
    blob: new Blob([new Uint8Array(bytes)], {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }),
    filename: bookFilename("docx"),
    blocks: blocks.length,
  };
}
