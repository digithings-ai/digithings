/**
 * Thesis route segments pre-rendered at build time when using `output: 'export'`.
 * Add stable thesis ids here so `/portfolio/theses/{thesisId}` has a static HTML file
 * (direct loads / refresh on static hosting). `_unlinked` is always included.
 */
export const THESIS_BUILD_STATIC_PARAMS: { thesisId: string }[] = [{ thesisId: '_unlinked' }];
