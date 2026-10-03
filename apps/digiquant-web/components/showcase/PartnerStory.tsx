import { PARTNER_SLOTS } from "@/lib/showcase";

/** Partner narrative placeholders — embeds land later; this is the story beat. */
export function PartnerStory() {
  return (
    <div className="bento">
      {PARTNER_SLOTS.map((slot) => (
        <article key={slot.id} className="bento__cell bento__cell--static">
          <p className="bento__kicker">{slot.kicker}</p>
          <h3 className="bento__title">{slot.title}</h3>
          <p className="bento__body">{slot.body}</p>
          <p className="bento__cta text-ink-mute">
            Embed placeholder
          </p>
        </article>
      ))}
    </div>
  );
}
