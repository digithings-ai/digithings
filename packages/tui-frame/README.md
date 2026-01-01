# @digithings/tui-frame

One declaration of a recorded TUI frame, shared by the TUI exporters and the
dashboard (DIG-2698, ADR D7).

A TUI preview is a recorded frame, not a live socket: the client renders itself
through OpenTUI `captureCharFrame()`, crops the pane it wants to show, and
writes the record below. The dashboard renders that frame as text in Geist
Mono, byte for byte.

Before this package the record was declared in `clients/digichat-tui`,
`clients/digiquant-tui` and `apps/dashboard`, and the copies drifted: the
dashboard documented `width` as the terminal width while the producers wrote
the ink extent of the crop (70 columns for a 100-column terminal).

## What is shared, and what is not

Shared here:

- `RecordedFrame`, `makeRecordedFrame`, `serializeRecordedFrame` and
  `isRecordedFrame` — the record and its guard.
- `writeRecordedFrame` (`src/write.ts`) — the one export path: validate the
  record, create the parent directory, write the serialized bytes. Both
  exporters had a copy of that before, one through `Bun.write` and one through
  `node:fs`, and neither refused a record the dashboard would drop. It is
  deliberately **not** re-exported from `index.ts`: the dashboard imports this
  package in the browser, so a `node:fs` specifier must stay out of that entry.
- `startFixtureApi` — the deterministic fixture server each exporter reads
  through. It binds an ephemeral port by default, so two exporters can run at
  once; the URL it returns is the base the client points itself at.
- `parseFlags`, `positiveInt`, `zonedIso` — the exporter command line.

Deliberately per client: the crop geometry and the render harness. Each client
renders a different app and crops a different pane, so those cannot be one
function without inventing an abstraction for two call sites. The clients do not
re-export the record either: a second export surface is how the copies drifted
in the first place.

## Reproducible fixtures

`capturedAt` is the only field that moves between two captures. Pass
`--captured-at <ISO-with-zone>` to the exporter to pin it, and the committed
fixture reproduces byte for byte. The exporter tests compare the committed
fixture with a fresh capture at the same pinned time.

## Tests

```sh
bun test
```

The package has no dependencies; it uses `node:http` only, so both Bun and Node
can run it.
