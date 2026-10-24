// The node side of scripts/paperclip_heartbeat_runs_redact_secrets.py.
//
// It runs the paperclip server's own redaction rule over the payloads it is
// given: `redactEventPayload` from `server/src/redaction.ts`, the helper the
// server runs on the run event write path and the one DIG-5227 puts on the
// run result write path. The payloads arrive on stdin, one JSON document per
// line, and the redacted payloads leave on stdout, one per line.
//
// Nothing but the payloads crosses the pipe, and no payload is printed: the
// harness writes the redacted document and nothing else. It never writes an
// error message either, because a JSON parse error quotes the text it
// choked on, and that text is the payload. Only the name of the error
// leaves, so a failure can be reported without leaking what it was about.
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const bundlePath = process.argv[2];
const { redactEventPayload } = require(bundlePath);

function reportFailure(error) {
  const name = error && error.name ? String(error.name) : "Error";
  process.stderr.write(`paperclip redact harness: ${name}\n`);
}

let buffer = "";

function handle(line) {
  if (!line.trim()) return;
  let output;
  try {
    const redacted = redactEventPayload(JSON.parse(line));
    output = JSON.stringify(redacted === undefined ? null : redacted);
  } catch (error) {
    reportFailure(error);
    output = JSON.stringify({ __redact_failed__: true });
  }
  process.stdout.write(`${output}\n`);
}

process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  buffer += chunk;
  let index;
  while ((index = buffer.indexOf("\n")) >= 0) {
    handle(buffer.slice(0, index));
    buffer = buffer.slice(index + 1);
  }
});
process.stdin.on("end", () => {
  handle(buffer);
});
