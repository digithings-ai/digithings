// @vitest-environment happy-dom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocked = vi.hoisted(() => ({
  pdf: vi.fn(),
  html: vi.fn(),
  docx: vi.fn(),
  saved: vi.fn(),
}));

vi.mock("@/lib/book/download-pdf", () => ({
  buildBookPdf: mocked.pdf,
  prefetchPrintedEdition: () => {},
}));
vi.mock("@/lib/book/export-html", () => ({ buildBookHtml: mocked.html }));
vi.mock("@/lib/book/export-docx", () => ({ buildBookDocx: mocked.docx }));
vi.mock("@/lib/book/export-file", () => ({
  bookFilename: (extension: string) => `the-digithings-book-light.${extension}`,
  saveBlob: mocked.saved,
}));

import BookExportBar, { BOOK_EXPORT_FORMATS } from "./BookExportBar";

const file = (name: string, bytes: string) => ({
  blob: new Blob([bytes]),
  filename: `the-digithings-book-light.${name}`,
});

beforeEach(() => {
  mocked.pdf.mockReset().mockResolvedValue({ ...file("pdf", "%PDF-1.7"), pages: 19 });
  mocked.html.mockReset().mockResolvedValue({ ...file("html", "<!doctype html>"), bytes: 24 });
  mocked.docx.mockReset().mockResolvedValue({ ...file("docx", "PK"), blocks: 7 });
  mocked.saved.mockReset();
});

afterEach(cleanup);

describe("BookExportBar", () => {
  it("offers every declared format as its own button, each naming its file", () => {
    render(<BookExportBar />);

    expect(screen.getByRole("group", { name: "export the book" })).toBeTruthy();
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(BOOK_EXPORT_FORMATS.length);

    // The format list, exercised end to end: what the reader sees on each cell,
    // and the file name the cell promises to produce.
    expect(BOOK_EXPORT_FORMATS.map((format) => format.label)).toEqual(["PDF", "HTML", "DOCX"]);
    for (const [index, format] of BOOK_EXPORT_FORMATS.entries()) {
      const button = buttons[index];
      const expectedName = `the-digithings-book-light.${format.extension}`;
      expect(button.textContent).toBe(format.label);
      expect(button.getAttribute("title")).toBe(`download ${expectedName}`);
      expect(button.getAttribute("aria-label")).toBe(
        `download the book as ${format.label} — ${expectedName}`,
      );
      // A cell is a mark and a name, not a paragraph.
      expect(button.querySelector("svg")).not.toBeNull();
    }
  });

  it("builds and saves the format whose button was pressed, and no other", async () => {
    render(<BookExportBar />);

    const cases = [
      { label: "PDF", builder: mocked.pdf, extension: "pdf" },
      { label: "HTML", builder: mocked.html, extension: "html" },
      { label: "DOCX", builder: mocked.docx, extension: "docx" },
    ] as const;

    for (const { label, builder, extension } of cases) {
      const before = cases.reduce(
        (total, entry) => total + entry.builder.mock.calls.length,
        0,
      );
      screen.getByRole("button", { name: new RegExp(`as ${label} `) }).click();

      await waitFor(() => expect(builder).toHaveBeenCalledTimes(1));
      expect(mocked.saved).toHaveBeenLastCalledWith(expect.any(Blob), `the-digithings-book-light.${extension}`);
      // One press, one builder: a format that quietly built two files is a bug.
      const after = cases.reduce((total, entry) => total + entry.builder.mock.calls.length, 0);
      expect(after - before).toBe(1);
      await waitFor(() =>
        expect(screen.getByRole("status").textContent).toBe(
          `saved the-digithings-book-light.${extension}`,
        ),
      );
    }
  });

  it("tells the reader when a format could not be built", async () => {
    mocked.docx.mockRejectedValueOnce(new Error("no pagination"));
    render(<BookExportBar />);

    screen.getByRole("button", { name: /as DOCX / }).click();

    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toBe("couldn't build the docx — try again"),
    );
    expect(mocked.saved).not.toHaveBeenCalled();
  });
});
