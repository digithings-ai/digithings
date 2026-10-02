/** Contract §1/§2 shared shapes: error envelope + provenance. Re-exported from ./index. */

export type ErrorCode = "bad_request" | "unauthorized" | "forbidden" | "not_found" | "upstream_empty" | "internal";

export interface Provenance {
  source: string;
  tip_date: string | null;
  contract: "finalized_accounting" | "legacy_estimate" | null;
  seam: boolean;
  marks: "stored" | "market_api" | "unavailable";
}

const ERROR_STATUS: Record<ErrorCode, number> = {
  bad_request: 400,
  unauthorized: 401,
  forbidden: 403,
  not_found: 404,
  upstream_empty: 502,
  internal: 500,
};

/** Contract section 2 error envelope — the only failure shape. */
export function errorResponse(
  code: ErrorCode,
  message: string,
  retrievalPin: string | null,
  details: Record<string, unknown> = {},
): Response {
  return Response.json(
    { error: { code, message, details, retrieval_pin: retrievalPin } },
    { status: ERROR_STATUS[code] },
  );
}

/** Contract section 1 provenance object — every success carries one. */
export function buildProvenance(partial: Partial<Provenance> & Pick<Provenance, "source">): Provenance {
  return {
    tip_date: null,
    contract: null,
    seam: false,
    marks: "unavailable",
    ...partial,
  };
}
