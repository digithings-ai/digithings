"use client";

import { RepoActivity, type RepoContributor, type RepoModuleRelease } from "@digithings/ui";
import { CONTRIBUTING_URL, REPO_CLONE, REPO_URL, repoActivity } from "@/lib/repoActivity";
import { useModuleReleases } from "@/lib/moduleReleases";

/**
 * The client shell for the open-source band's version rail (#4429).
 *
 * `RepoActivity` is already a client component, but the live releases read has
 * to happen in this app — the kit must not carry a fetch it cannot test, and it
 * cannot know the repo's modules. So the band splits: `OpenSource` (server, in
 * Sections.tsx) owns the committed list and renders this shell, which swaps the
 * declared versions for the live ones after hydration. The committed list is
 * the first paint and the fallback; a failed read changes nothing.
 */
export function OpenSourceLive({
  moduleReleases,
  contributor,
}: {
  moduleReleases: RepoModuleRelease[];
  contributor: RepoContributor;
}) {
  const releases = useModuleReleases(moduleReleases);
  return (
    <RepoActivity
      variant="activity"
      snapshot={repoActivity}
      repoUrl={REPO_URL}
      cloneCommand={REPO_CLONE}
      contributingUrl={CONTRIBUTING_URL}
      moduleReleases={releases}
      contributor={contributor}
      className="min-w-0"
    />
  );
}
