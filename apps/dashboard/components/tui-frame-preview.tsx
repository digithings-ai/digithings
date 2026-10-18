/**
 * D9 recorded-frame preview: TUIs (DIG-2698).
 *
 * Renders a recorded terminal frame (OpenTUI `captureCharFrame()` output) as
 * Geist Mono text. Recorded frames only — no live socket in 1.0 (ADR D7).
 * The frame is data: rendered byte-for-byte, never interpreted.
 */

type TuiFramePreviewProps = {
  /** Which TUI the frame was recorded from (label only). */
  source: string;
  /** Recorded frame text, exactly as `captureCharFrame()` returned it. */
  frame: string;
};

export default function TuiFramePreview({ source, frame }: TuiFramePreviewProps) {
  return (
    <section data-tui-frame-preview={source}>
      <pre className="font-mono">{frame}</pre>
    </section>
  );
}
