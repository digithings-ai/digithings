/**
 * A failed /embed answer must render, never download. The chat frame (and a
 * phone opening the same URL) navigates to /embed as a document; when the
 * container is down the Worker answers with a JSON or plain-text body, or
 * passes the platform's own error through, and a mobile browser handed a
 * non-HTML document (or any Content-Disposition) may offer it as a file.
 *
 * For document navigations only, an error status that is not already HTML is
 * re-served as a short HTML page: same status, same Retry-After, never a
 * Content-Disposition, and no internal detail in the body (the cause stays in
 * the Worker log). API callers (fetch/XHR, no document destination) get the
 * original response untouched.
 */

export const FRAME_SAFE_ERROR_HTML =
  '<!doctype html><html lang="en"><head><meta charset="utf-8">' +
  '<meta name="viewport" content="width=device-width, initial-scale=1">' +
  "<title>digichat</title></head><body>" +
  "<p>The chat could not load. Please try again in a moment.</p>" +
  "</body></html>";

const DOCUMENT_DESTINATIONS = new Set(["document", "iframe", "frame", "embed"]);

/** True when the browser is loading this URL as a page or a frame. */
export function isDocumentRequest(request: Request): boolean {
  const dest = request.headers.get("sec-fetch-dest");
  if (dest) return DOCUMENT_DESTINATIONS.has(dest.toLowerCase());
  // Older browsers send no Fetch Metadata: fall back to what they accept.
  return (request.headers.get("accept") ?? "").toLowerCase().includes("text/html");
}

function isHtml(contentType: string | null): boolean {
  return (contentType ?? "").toLowerCase().split(";")[0]!.trim() === "text/html";
}

export function frameSafeErrorResponse(request: Request, res: Response): Response {
  if (res.status < 400 || !isDocumentRequest(request)) return res;
  const html = isHtml(res.headers.get("content-type"));
  const disposition = res.headers.has("content-disposition");
  if (html && !disposition) return res;
  const headers = new Headers(res.headers);
  headers.delete("content-disposition");
  headers.delete("content-length");
  headers.delete("content-encoding");
  headers.set("content-type", "text/html; charset=utf-8");
  headers.set("x-content-type-options", "nosniff");
  // An HTML error page keeps its own body; anything else is replaced, so a
  // JSON or platform message never paints in the frame.
  return new Response(html ? res.body : FRAME_SAFE_ERROR_HTML, {
    status: res.status,
    statusText: res.statusText,
    headers,
  });
}
