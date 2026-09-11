"use client";

/**
 * Pagination specimen — the numbered page trail from @digithings/web, live.
 * Controlled (`page` + `pageCount`) with buttons here; pass `hrefForPage`
 * for links. First / last with an ellipsis around the current page, prev /
 * next disabling at the edges, the current page the one loud control (ink
 * fill). Dress is `.ctl-pagination*` in the package core sheet.
 */
import { useState } from "react";
import { Pagination } from "@digithings/web";

const PAGE_COUNT = 8;

export function PaginationReference() {
  const [page, setPage] = useState(3);
  return (
    <section className="section-block" id="pagination">
      <p className="kicker">{"// pagination"}</p>
      <h2 className="title">Long lists end somewhere.</h2>
      <p className="section-copy">
        <code>Pagination</code> from <code>@digithings/web</code> walks a long list: the window
        keeps first, last, and one neighbor each side of the current page. Click through — prev
        locks on page one, next on page eight.
      </p>

      <div className="mt-[1.2rem] flex flex-col gap-[0.7rem]">
        <Pagination page={page} pageCount={PAGE_COUNT} onPageChange={setPage} />
        <p className="font-mono text-[0.72rem] text-ink-mute">
          Page {page} of {PAGE_COUNT}
        </p>
      </div>
    </section>
  );
}
