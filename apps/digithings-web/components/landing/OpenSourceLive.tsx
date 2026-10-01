"use client";

import { RepoActivity, type RepoContributor } from "@digithings/ui";
import { CONTRIBUTING_URL, REPO_CLONE, REPO_URL, repoActivity } from "@/lib/repoActivity";

/**
 * The client shell for the open-source band (#4429).
 *
 * `RepoActivity` is already a client component; this thin shell keeps the band's
 * props in one place and lets the server section own the maintainer credit.
 */
export function OpenSourceLive({ contributor }: { contributor: RepoContributor }) {
  return (
    <RepoActivity
      variant="activity"
      snapshot={repoActivity}
      repoUrl={REPO_URL}
      cloneCommand={REPO_CLONE}
      contributingUrl={CONTRIBUTING_URL}
      contributor={contributor}
      className="min-w-0"
    />
  );
}
