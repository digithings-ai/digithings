/**
 * Responses.
 *
 * OTLP/HTTP is strict about the response encoding: a client decodes what it
 * sent. A protobuf source that receives JSON sees a decode failure and may
 * retry for ever, so both encodings are produced here rather than the JSON body
 * being used for everything.
 *
 * Nothing in a response echoes a token, a tenant record or span content.
 */
import { encodeTraceResponse } from "./protobuf";

/**
 * The largest request body the receiver will parse.
 *
 * OTLP/HTTP is a server-decides limit; 4 MiB is comfortably above a normal
 * export batch (the SDKs ship 512-span batches, well under this) and far below
 * the platform's request ceiling. It exists so one caller cannot make the
 * Worker buffer an arbitrary body, not to shape traffic.
 */
export const MAX_BODY_BYTES = 4 * 1024 * 1024;

const JSON_TYPE = "application/json";
const PROTOBUF_TYPE = "application/x-protobuf";

export type Encoding = "json" | "protobuf";

function jsonResponse(
  status: number,
  body: unknown,
  headers: Record<string, string> = {},
): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": JSON_TYPE, ...headers },
  });
}

export const respond = {
  json: jsonResponse,

  /**
   * A successful export, in the encoding the source used.
   *
   * `rejectedSpans` is carried in OTLP's own `partialSuccess`: the spans were
   * dropped (malformed or too large for one queue message) and the source can
   * see the count instead of assuming the whole batch was stored.
   */
  success(encoding: Encoding, rejectedSpans: number): Response {
    if (encoding === "protobuf") {
      const body = encodeTraceResponse(
        rejectedSpans,
        rejectedSpans > 0 ? "spans rejected by digitrace-ingest" : "",
      );
      return new Response(body, {
        status: 200,
        headers: { "content-type": PROTOBUF_TYPE },
      });
    }
    if (rejectedSpans <= 0) return jsonResponse(200, {});
    return jsonResponse(200, {
      partialSuccess: {
        rejectedSpans,
        errorMessage: "spans rejected by digitrace-ingest",
      },
    });
  },

  /** A refused request, in the encoding the source used. */
  error(encoding: Encoding, status: number, message: string): Response {
    if (encoding === "protobuf") {
      return new Response(new Uint8Array(0), {
        status,
        headers: { "content-type": PROTOBUF_TYPE },
      });
    }
    return jsonResponse(status, { error: message });
  },
};
