/**
 * Re-export of the shared page-context sanitizer (DIG-3695: moved to
 * `@digithings/catalog`). Local importers (`@/lib/page-context-sanitize`)
 * keep working unchanged. Keep `public/widget.js` in sync with the walk.
 */
export * from "@digithings/catalog/page-context-sanitize";
