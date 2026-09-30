import { MediaFrame } from "@digithings/ui";

/**
 * Media frame — the specimen for the shared <MediaFrame/> (@digithings/ui,
 * data-layout): a 16:9 artboard in terminal chrome for a recording or a still.
 * With no `src` it is a designed placeholder (title bar, hairline grid, corner
 * ticks, a disabled play glyph, the caller's "recording to come" label); with a
 * `src` it is a native video with controls, muted, inline, preload none and
 * never autoplay. The badge is a required prop. No media ships with the
 * specimen, so only the placeholder state renders.
 */
export function MediaFrameReference() {
  return (
    <section className="section-block" id="media-frame">
      <p className="kicker">{"// media frame"}</p>
      <h2 className="title">A frame for a recording that does not exist yet.</h2>
      <p className="section-copy">
        The placeholder is a first-class state: it says what is missing and shows nothing the
        recording would not. Give it a src and the same frame carries a native, non-autoplaying
        video with the poster you pass.
      </p>
      <div className="mt-[1.2rem] max-w-[46rem]">
        <MediaFrame
          title="sample walkthrough"
          badge="Placeholder · no recording yet"
          placeholderLabel="recording to come"
          caption="A short screen recording of the sample flow will replace this frame."
        />
      </div>
    </section>
  );
}
