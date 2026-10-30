// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";

import { buildBookHtml } from "./export-html";

const FIGURE = "data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%2F%3E";

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

describe("buildBookHtml", () => {
  it("carries the recoloured figures into the file without re-fetching them", async () => {
    document.body.innerHTML = `
      <div class="book-live__stage">
        <div class="pagedjs_pages">
          <div class="pagedjs_page">
            <figure data-book-diagram="">
              <img class="book-figure__light" src="${FIGURE}" alt="">
              <img class="book-figure__dark" src="${FIGURE}" alt="">
              <figcaption>one request, one story</figcaption>
            </figure>
          </div>
        </div>
      </div>`;
    // The site's CSP has no data: in connect-src: a fetch of the figure is the
    // request the browser refuses, which used to leave the file with no figures.
    const fetchSpy = vi.fn(async () => {
      throw new TypeError("refused by connect-src");
    });
    vi.stubGlobal("fetch", fetchSpy);

    const { blob } = await buildBookHtml();
    const html = await blob.text();

    expect(html.match(/<img /g)?.length).toBe(2);
    expect(html).toContain(FIGURE);
    expect(fetchSpy).not.toHaveBeenCalledWith(expect.stringMatching(/^data:/));
  });
});
