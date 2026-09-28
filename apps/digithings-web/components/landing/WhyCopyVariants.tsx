/**
 * The three why-band takes (A/B/C) as full guided walks, stacked for review,
 * plus Study D — the traditional stack drawn accurately, their side only.
 * Each version gets the real tour so the pick is made on the experience, not
 * on excerpts. The A/B/C specs, tags and captions are shared; the versions
 * differ in headline, lede and walks. Study D runs ahead of all three: it is
 * where the "their" drawing gets frozen before any owned side is redrawn
 * against it.
 *
 * Server component: `ArchitectureTour` is the only client piece.
 */

import { ArchitectureTour } from "@digithings/ui";

import { CONVENTIONAL_ARCH, DIGITHINGS_ARCH } from "@/lib/whyStack";
import { WHY_COPY_VERSIONS, type WhyCopyVersion } from "@/lib/whyCopyVariants";
import { TRADITIONAL_ARCH, TRADITIONAL_STEPS } from "@/lib/whyLeftStudy";
import { RagCostPanel } from "@/components/landing/RagCostPanel";
import { StackConfigurator } from "@/components/landing/StackConfigurator";

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
      <section aria-label="Study D — the traditional stack, accurately" className="line-b">
        <div className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[0.5rem] px-[var(--page-pad)] pt-[2.5rem]">
          <span className={VERSION_LABEL}>study D · their side only</span>
          <p className={LEDE}>
            The traditional AI stack drawn the way an architect would draw it — your data
            sources in, one provider wall app-to-silicon, vectors and embeddings captured
            inside. Five steps: locked in, not modular, more expensive, then the trend.
          </p>
        </div>
        <div className="whyx">
          <div className="whyx__block">
            <div className="whyx__tours">
              <div className="whyx__tour">
                <ArchitectureTour
                  header={
                    <>
                      <h2 className={HEADLINE}>
                        {/* No why-rent/why-own hooks here: those track the walked
                            side of a two-side tour, and a single-side study has
                            no swap — both halves stay bright. */}
                        <span className="text-ink">The traditional AI stack,</span>{" "}
                        <span className="text-ink">drawn honestly.</span>
                      </h2>
                      <p className={LEDE}>
                        Your product, your data — and one provider wall around everything
                        else, from the gateway down to the GPUs. Scroll to walk it the way
                        the lock-in actually works.
                      </p>
                    </>
                  }
                  sides={[
                    {
                      spec: TRADITIONAL_ARCH,
                      steps: TRADITIONAL_STEPS,
                      tag: "their stack",
                      caption: "Your data in · their wall around the rest",
                    },
                  ]}
                  variant="camera"
                />
              </div>
            </div>
          </div>
        </div>
        <RagCostPanel />
      </section>
      <StackConfigurator />
      {WHY_COPY_VERSIONS.map((version) => (
        <VersionBand key={version.id} version={version} />
      ))}
    </>
  );
}
