/**
 * `pagedjs` ships no TypeScript declarations.
 *
 * Only the one call this app makes is declared. The shape is deliberately
 * narrow: `Previewer` paginates one element and the chunker tears that
 * pagination down, and a wider `any` would let a caller reach for API this
 * route has no business using.
 */
declare module "pagedjs" {
  export interface Chunker {
    /** Remove the page boxes the chunker created. */
    destroy(): Promise<void>;
  }

  export class Previewer {
    /**
     * Paginate `content` inside `renderTo`.
     *
     * The argument order is `content, stylesheets, renderTo` — read off
     * `pagedjs/src/polyfill/previewer.js`. `stylesheets` is the middle
     * argument, not `renderTo`; `undefined` asks pagedjs to strip the page's
     * own stylesheets.
     *
     * `content` is ONE node or its HTML, never an array: it goes straight to
     * `createTreeWalker`, which rejects anything that is not a Node. Both
     * shapes of that mistake were measured here rather than guessed.
     */
    preview(content: HTMLElement | string, stylesheets: string[] | undefined, renderTo: HTMLElement): Promise<Chunker>;
  }
}
