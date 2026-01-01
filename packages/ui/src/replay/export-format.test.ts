/**
 * @vitest-environment happy-dom
 */
import { describe, expect, it, vi } from "vitest";

import { UNSUPPORTED_EXPORT_FORMAT, applyExportSlash } from "./export-format";

describe("applyExportSlash", () => {
  it("shows an unsupported-format error for pdf and any other unknown format", () => {
    const doc = document.implementation.createHTMLDocument("chat");
    doc.body.append(doc.createElement("p"));
    const html = vi.fn();
    const markdown = vi.fn();
    applyExportSlash("pdf", doc, { html, markdown });
    expect(html).not.toHaveBeenCalled();
    expect(markdown).not.toHaveBeenCalled();
    expect(doc.querySelector("[role='alert']")?.textContent).toBe(UNSUPPORTED_EXPORT_FORMAT);
    expect(doc.querySelector("[role='alert']")?.textContent).toMatch(/unsupported format/i);

    applyExportSlash("docx", doc, { html, markdown });
    expect(html).not.toHaveBeenCalled();
    expect(markdown).not.toHaveBeenCalled();
    expect(doc.querySelector("[data-slot='snapshot-export-error']")?.textContent).toBe(
      UNSUPPORTED_EXPORT_FORMAT,
    );
  });

  it("saves html or markdown for the known formats", () => {
    const doc = document.implementation.createHTMLDocument("chat");
    const html = vi.fn();
    const markdown = vi.fn();
    applyExportSlash(" HTML ", doc, { html, markdown });
    expect(html).toHaveBeenCalledOnce();
    expect(markdown).not.toHaveBeenCalled();

    applyExportSlash("md", doc, { html, markdown });
    applyExportSlash("markdown", doc, { html, markdown });
    applyExportSlash("", doc, { html, markdown });
    expect(markdown).toHaveBeenCalledTimes(3);
    expect(html).toHaveBeenCalledOnce();
    expect(doc.querySelector("[role='alert']")).toBeNull();
  });
});
