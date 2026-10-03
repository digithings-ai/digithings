import { VIDEO_SLOTS } from "@/lib/showcase";

/** Film slots — placeholders until method/capability films land. */
export function VideoSlots() {
  return (
    <div className="bento min-[960px]:grid-cols-3">
      {VIDEO_SLOTS.map((slot) => (
        <article key={slot.id} className="bento__cell bento__cell--static">
          <div
            className="bento__thumb relative aspect-video border border-hair bg-surface-2"
            aria-hidden="true"
          >
            <span className="absolute inset-0 grid place-items-center font-mono text-[0.68rem] uppercase tracking-[0.16em] text-ink-mute">
              film forthcoming
            </span>
          </div>
          <p className="bento__kicker">{slot.kicker}</p>
          <h3 className="bento__title">{slot.title}</h3>
          <p className="bento__body">{slot.body}</p>
        </article>
      ))}
    </div>
  );
}
