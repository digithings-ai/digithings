/**
 * `@digithings/tui-frame` — the one declaration of a recorded TUI frame
 * (DIG-2698, ADR D7), shared by every TUI exporter and the dashboard.
 *
 * ADR D7: a TUI preview is a recorded frame, not a live socket. Each client
 * renders itself through OpenTUI `captureCharFrame()`, crops the pane it wants
 * to show, and writes the record below. The dashboard reads that record and
 * renders the frame as text in Geist Mono.
 *
 * The record used to be declared once per client and a third time in the
 * dashboard, and the copies drifted. It lives here so that cannot happen.
 */

export {
  isRecordedFrame,
  makeRecordedFrame,
  serializeRecordedFrame,
  type CroppedFrame,
  type RecordedFrame,
} from "./record";

export {
  startFixtureApi,
  type FixtureApi,
  type FixtureAnswer,
  type FixtureRoute,
  type FixtureServerOptions,
} from "./fixture-server";

export { parseFlags, positiveInt, zonedIso } from "./flags";
