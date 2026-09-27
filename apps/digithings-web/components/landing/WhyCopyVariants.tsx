/**
 * The three why-band takes (A/B/C) as full guided walks, stacked for review.
 * Each version gets the real tour — headline, lede, rented glow walk, owned
 * camera walk — so the pick is made on the experience, not on excerpts. The
 * specs, tags and captions are shared; the versions differ in headline, lede
 * and walks, which is the comparison under review.
 *
 * Server component: `ArchitectureTour` is the only client piece.
 */

import { ArchitectureTour } from "@digithings/ui";

import { CONVENTIONAL_ARCH, DIGITHINGS_ARCH } from "@/lib/whyStack";
import { WHY_COPY_VERSIONS, type WhyCopyVersion } from "@/lib/whyCopyVariants";

const HEADLINE = "m-0 font-mono text-[clamp(1.3rem,2.4vw,1.85rem)] font-medium leading-[1.2] tracking-[-0.02em] text-ink";
const LEDE = "m-0 max-w-[var(--measure-prose)] text-[0.9rem] leading-[1.7] text-ink-soft";
const VERSION_LABEL = "font-mono text-[0.68rem] uppercase tracking-[0.08em] text-ink-mute";

function VersionBand({ version }: { version: WhyCopyVersion }) {
  return (
    <section aria-label={`Version ${version.id} — ${version.name}`} className="line-b">
      <div className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[0.5rem] px-[var(--page-pad)] pt-[2.5rem]">
        <span className={VERSION_LABEL}>
          version {version.id} · {version.name}
        </span>
        <p className={LEDE}>{version.blurb}</p>
      </div>
      <div className="whyx">
        <div className="whyx__block">
          <div className="whyx__tours">
            <div className="whyx__tour">
              <ArchitectureTour
                header={
                  <>
                    <h2 className={HEADLINE}>
                      <span className="why-rent">{version.headline[0]}</span>{" "}
                      <span className="why-own">{version.headline[1]}</span>
                    </h2>
                    <p className={LEDE}>{version.lede}</p>
                  </>
                }
                sides={[
                  {
                    spec: CONVENTIONAL_ARCH,
                    steps: version.leftSteps,
                    tag: "their stack",
                    rail: "end",
                    caption: "Every edge metered — per-token · per-query · per-gigabyte",
                  },
                  {
                    spec: DIGITHINGS_ARCH,
                    steps: version.rightSteps,
                    tag: "digithings stack",
                    caption:
                      "Every box a module — take one or run them all · digibase under all of them",
                  },
                ]}
                variant="camera"
              />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export function WhyCopyVariants() {
  return (
    <>
      {WHY_COPY_VERSIONS.map((version) => (
        <VersionBand key={version.id} version={version} />
      ))}
    </>
  );
}
