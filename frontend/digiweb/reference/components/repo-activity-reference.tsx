/**
 * Repository activity — snapshot-first compact and detailed views of public
 * GitHub velocity. Three last-30-days counts, a current backlog, latest
 * release, and recent merged PRs / open issues. Optional live refresh never
 * blanks the snapshot. Consumes <RepoActivity/> from @digithings/web.
 */
import {
  RepoActivity,
  RepoHeatmap,
  REPO_ACTIVITY_DEMO,
  REPO_ACTIVITY_DEMO_CLONE,
  REPO_ACTIVITY_DEMO_CONTRIBUTING,
  REPO_ACTIVITY_DEMO_URL,
} from "@digithings/web";

export { RepoActivity, RepoHeatmap } from "@digithings/web";

export function RepoActivityReference() {
  return (
    <section className="section-block" id="repo-activity">
      <p className="kicker">{"// repository activity"}</p>
      <h2 className="title">A living repo, two densities.</h2>
      <p className="section-copy">
        Snapshot-first GitHub velocity: the committed figures always render, and a live refresh
        replaces them only when every request succeeds. Compact is a portfolio card — three
        30-day counts, latest release, stamp, a handful of merged PRs. Detailed splits last-30-days
        from the current backlog, then two columns of recent merged PRs and recently updated open
        issues. No stars, forks, or watchers.
      </p>

      <p className="kicker ra-specimen-kicker">{"// compact"}</p>
      <RepoActivity
        variant="compact"
        snapshot={REPO_ACTIVITY_DEMO}
        repoUrl={REPO_ACTIVITY_DEMO_URL}
      />

      <p className="kicker ra-specimen-kicker ra-specimen-kicker-next">{"// detailed"}</p>
      <RepoActivity
        variant="detailed"
        snapshot={REPO_ACTIVITY_DEMO}
        repoUrl={REPO_ACTIVITY_DEMO_URL}
        cloneCommand={REPO_ACTIVITY_DEMO_CLONE}
        contributingUrl={REPO_ACTIVITY_DEMO_CONTRIBUTING}
      />

      <p className="kicker ra-specimen-kicker ra-specimen-kicker-next">{"// contributions"}</p>
      <p className="section-copy">
        The heat element alone: a full year of contributions as small perfect squares — no radius,
        no borders, no gradients — empty track to full accent in categorical steps. Weeks run
        oldest left.
      </p>
      <RepoHeatmap pulls={REPO_ACTIVITY_DEMO.mergedPulls} weeks={53} />
    </section>
  );
}
