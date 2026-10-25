// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";

import { collectBlocks, docxBytes, type DocBlock } from "./export-docx";

function latin1(data: Uint8Array): string {
  return new TextDecoder("latin1").decode(data);
}

/** A page box as pagedjs leaves it: content inside `.pagedjs_page_content`. */
function page(html: string): string {
  return `<div class="pagedjs_page"><div class="pagedjs_sheet"><div class="pagedjs_page_content"><div>${html}</div></div></div></div>`;
}

describe("collectBlocks", () => {
  it("reads the page boxes in order, joins split paragraphs, and skips measurement copies", async () => {
    document.body.innerHTML = [
      page(
        `<section class="book-chapter"><div class="book-chapter__head"><p>01</p><h2>Why it scales</h2></div><p data-split-to="p1">A sentence that runs to the</p></section>`,
      ),
      page(
        `<section class="book-chapter"><p data-split-from="p1">bottom of the page.</p><ul><li><p>Nested point</p></li></ul>` +
          `<table><tbody><tr><th>Case</th><th>Cost</th></tr><tr><td>Own</td><td>Low</td></tr></tbody></table>` +
          `<p style="display:none">measurement copy</p></section>`,
      ),
    ].join("");

    const blocks = await collectBlocks(document);

    // Page one's paragraph survives the break as one paragraph, the nested
    // paragraph inside the list item is not a second bullet, and the hidden
    // measurement copy is not content.
    expect(blocks.map((block) => block.kind)).toEqual([
      "paragraph",
      "heading",
      "paragraph",
      "bullet",
      "table",
    ]);

    const texts = blocks.map((block) => ("runs" in block ? block.runs.map((run) => run.text).join("") : ""));
    expect(texts[1]).toBe("Why it scales");
    expect(texts[2]).toBe("A sentence that runs to the bottom of the page.");
    expect(texts[3]).toBe("Nested point");
    expect(texts.some((text) => text.includes("measurement copy"))).toBe(false);

    const tables = blocks.filter((block): block is Extract<DocBlock, { kind: "table" }> => block.kind === "table");
    // The header row and the body row are one table, not two.
    expect(tables).toHaveLength(1);
    expect(tables[0]?.rows.map((row) => row.map((cell) => cell.map((run) => run.text).join("")).join("|"))).toEqual([
      "Case|Cost",
      "Own|Low",
    ]);
  });
});

describe("docxBytes", () => {
  const blocks: DocBlock[] = [
    { kind: "heading", level: 1, runs: [{ text: "Why & how" }] },
    { kind: "paragraph", runs: [{ text: "Plain " }, { text: "bold", bold: true }] },
    { kind: "bullet", runs: [{ text: "A point" }] },
    {
      kind: "table",
      rows: [
        [[{ text: "Case" }], [{ text: "Cost" }]],
        [[{ text: "Own" }], [{ text: "Low" }]],
      ],
    },
    { kind: "figure", data: new Uint8Array([1, 2, 3, 4]), width: 914400, height: 457200, alt: "a diagram" },
  ];

  it("is an OOXML package: a zip with the parts Word needs", () => {
    const archive = docxBytes(blocks);
    expect(archive[0]).toBe(0x50);
    expect(archive[1]).toBe(0x4b);

    const text = latin1(archive);
    for (const part of [
      "[Content_Types].xml",
      "_rels/.rels",
      "word/document.xml",
      "word/styles.xml",
      "word/_rels/document.xml.rels",
      "word/media/figure-1.png",
    ]) {
      expect(text).toContain(part);
    }
  });

  it("carries the words, escaped, with the Word structure around them", () => {
    const text = latin1(docxBytes(blocks));

    expect(text).toContain('<w:t xml:space="preserve">Why &amp; how</w:t>');
    expect(text).toContain('<w:pStyle w:val="Heading1"/>');
    expect(text).toContain("<w:b/>");
    expect(text).toContain('<w:pStyle w:val="ListParagraph"/>');
    expect(text).toContain("<w:tbl>");
    expect(text).toContain('<w:pgSz w:w="11906" w:h="16838"/>');
    // The figure is a real drawing relationship, not a placeholder.
    expect(text).toContain('<a:blip r:embed="rId2"/>');
    expect(text).toContain('Target="media/figure-1.png"');
  });
});
