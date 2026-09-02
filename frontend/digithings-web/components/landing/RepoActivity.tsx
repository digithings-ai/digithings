import { ChatCopyButton, GitHubGlyph, Reveal } from "@digithings/web";
import {
  CONTRIBUTING_URL,
  REPO_CLONE,
  REPO_URL,
  cloneParts,
  grouped,
  isoDay,
  repoActivity,
} from "@/lib/repoActivity";

/**
 * `// the repository` — the shipped-recently list, the clone line, and the
 * contributor CTA.
 *
 * The page already argues that the stack is open; this is the section that lets a
 * reader check. Each row is a `feat` commit on `main` in the last 30 days, linked
 * to the pull request that carried it, so "maintained in the open" is a claim with
 * a receipt attached rather than an adjective.
 *
 * Scopes are shown as-authored and unfiltered — infrastructure ones like `ci` and
 * `brand` appear beside product ones, and an unscoped `feat:` shows no scope at all
 * rather than being assigned an invented one. Curating the list down to the
 * product-sounding entries would make it marketing; leaving it whole makes it
 * evidence, and the breadth is itself the point about how the repo is maintained.
 *
 * Server component apart from <ChatCopyButton>, which is a client island from the
 * shared chat family (its `.chat-md-copy` styling is already imported by
 * globals.css). Placed low on the page, well clear of the #metrics odometer, so the
 * two number-bearing blocks never read as one restated twice.
 */
export function RepoActivity() {
  const a = repoActivity;
  const [cloneHead, cloneTail] = cloneParts();

  return (
    <section className="section" id="repository">
      <div className="wrap">
        <Reveal className="section-head center">
          <span className="kicker">{"// the repository"}</span>
          <h2>Maintained in the open.</h2>
          {/* The band above has room for figures but not for their scope. This is
              where the pairing the figures exist for gets stated in full: both
              numbers, each with the period it covers, in one sentence. */}
          <p>
            One MIT-licensed monorepo, public and moving — {grouped(a.issuesOpen)} issues open
            today against {grouped(a.issuesClosed)} closed in the last {a.windowDays} days.
            Below are the most recent features to land on{" "}
            <code className="font-mono text-ink">{a.branch}</code> — each one a pull request you
            can open and read, not a changelog entry we wrote about ourselves. Figures are a
            snapshot taken {isoDay(a.generatedAt)}.
          </p>
        </Reveal>

        <div className="mx-auto mt-[2rem] grid max-w-[980px] gap-[1.6rem] md:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
          <Reveal>
            <div className="font-mono text-[0.7rem] uppercase tracking-[0.16em] text-ink-mute">
              shipped recently
            </div>
            <ol className="mt-[0.9rem] border-t border-hair" role="list">
              {a.features.map((f) => (
                <li
                  key={f.pr}
                  className="flex flex-wrap items-baseline gap-x-[0.7rem] gap-y-[0.2rem] border-b border-hair py-[0.7rem]"
                >
                  <a
                    className="font-mono text-[0.78rem] text-accent [text-underline-offset:2px] hover:underline"
                    href={`${REPO_URL}/pull/${f.pr}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    #{f.pr}
                  </a>
                  <span className="min-w-0 flex-1 text-[0.94rem] leading-[1.5] text-ink-soft">
                    {f.summary}
                  </span>
                  {/* An unscoped `feat:` shows its date alone. The first draft
                      fell back to "core", which invents a scope the author never
                      wrote — and #1934 landed unscoped, so it was already wrong. */}
                  <span className="font-mono text-[0.7rem] text-ink-mute">
                    {f.scope ? `${f.scope} · ` : ""}
                    {isoDay(f.date)}
                  </span>
                </li>
              ))}
            </ol>
          </Reveal>

          <Reveal className="flex flex-col gap-[1.4rem]">
            <div>
              <div className="font-mono text-[0.7rem] uppercase tracking-[0.16em] text-ink-mute">
                run it yourself
              </div>
              {/* Wraps rather than scrolls: at this column width the one-line
                  version clipped mid-URL ("…/digithings-ai/di"), which reads as
                  broken even though the copy button carried the whole thing. The
                  <wbr/> is the only break opportunity, so it breaks after the org
                  slash instead of mid-word — and stays on one line where it fits.
                  The copied payload is REPO_CLONE and is unaffected by the split. */}
              <div className="mt-[0.9rem] flex items-start gap-[0.6rem] rounded-none border border-hair px-[0.75rem] py-[0.6rem]">
                <code className="min-w-0 flex-1 font-mono text-[0.74rem] leading-[1.5] text-ink-soft">
                  {cloneHead}
                  <wbr />
                  {cloneTail}
                </code>
                <ChatCopyButton text={REPO_CLONE} ariaLabel="Copy the clone command" />
              </div>
              {a.latestRelease ? (
                <p className="mt-[0.7rem] font-mono text-[0.72rem] text-ink-mute">
                  latest release{" "}
                  <a
                    className="text-ink [text-underline-offset:2px] hover:text-accent hover:underline"
                    href={a.latestRelease.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {a.latestRelease.tag}
                  </a>{" "}
                  · {isoDay(a.latestRelease.publishedAt)}
                </p>
              ) : null}
            </div>

            <div>
              <div className="font-mono text-[0.7rem] uppercase tracking-[0.16em] text-ink-mute">
                contribute
              </div>
              <p className="mt-[0.7rem] text-[0.92rem] leading-[1.6] text-ink-soft">
                Issues are open and the branching model is written down. Pick one up, or
                open an issue for the module you need.
              </p>
              <div className="mt-[1rem] flex flex-wrap gap-[0.6rem]">
                <a className="btn btn-primary" href={CONTRIBUTING_URL} target="_blank" rel="noreferrer">
                  Contributing guide <span aria-hidden="true">→</span>
                </a>
                <a
                  className="btn btn-ghost inline-flex items-center gap-[0.45rem]"
                  href={`${REPO_URL}/issues`}
                  target="_blank"
                  rel="noreferrer"
                >
                  <GitHubGlyph width={14} height={14} />
                  Open issues
                </a>
              </div>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
