/**
 * CONTRACT.md section 1 and section 2 primitives: the error envelope, the
 * provenance builder and the common query params.
 *
 * These live OUTSIDE `src/index.ts` on purpose. A module-worker entrypoint
 * may export only `default` (plus named entrypoint classes): workerd builds
 * its entrypoint map from every top-level export of the entrypoint module
 * and throws `Incorrect type for map entry '<name>': the provided value is
 * not of type 'function or ExportedHandler'` for anything else, so a single
 * `export const` here-in-index makes the worker fail to bind at startup and
 * nothing can reach it (see #4986, "dashboard API crashes on startup").
 *
 * `src/entrypoint-exports.test.ts` pins that invariant.
 */

export type ErrorCode = "bad_request" | "not_found" | "upstream_empty" | "internal";

export interface Provenance {
  source: string;
  tip_date: string | null;
  contract: "finalized_accounting" | "legacy_estimate" | null;
  seam: boolean;
  marks: "stored" | "market_api" | "unavailable";
}

const ERROR_STATUS: Record<ErrorCode, number> = {
  bad_request: 400,
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

export interface CommonParams {
  asOf: string | null;
  retrievalPin: string | null;
}

const AS_OF_RE = /^\d{4}-\d{2}-\d{2}$/;

/**
 * Contract section 1 common query params. Throws a Response (the error
 * envelope) on malformed input so handlers can `catch (e) return e`.
 */
export function parseCommonParams(url: URL): CommonParams {
  const retrievalPin = url.searchParams.get("retrieval_pin");
  if (retrievalPin !== null && retrievalPin.length > 128) {
    throw errorResponse("bad_request", "retrieval_pin exceeds 128 characters", null, {
      max_length: 128,
    });
  }
  const asOf = url.searchParams.get("asOf");
  if (asOf !== null) {
    const d = new Date(`${asOf}T00:00:00Z`);
    if (!AS_OF_RE.test(asOf) || Number.isNaN(d.getTime()) || d.toISOString().slice(0, 10) !== asOf) {
      throw errorResponse("bad_request", "asOf must be a calendar date YYYY-MM-DD", retrievalPin, {
        asOf,
      });
    }
  }
  return { asOf, retrievalPin };
}