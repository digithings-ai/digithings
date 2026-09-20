import type { Metadata } from "next";
import Image from "next/image";
import { ContactMailto, CtaLink, PageHead } from "@digithings/ui";
import { DtFooter } from "@/components/DtFooter";
import { DT_CONTACT_EMAIL } from "@/app/_nav";
import { DtNav } from "@/components/DtNav";

export const metadata: Metadata = {
  title: "team — who builds digithings",
  description:
    "Meet the current maintainer of digithings and follow the project's work in the public " +
    "GitHub repository.",
};

// /team — a roster template with one entry. Adding a member is one object in
// MEMBERS plus one vendored avatar file; the layout takes the second card
// without edits (single-column below 720px, two up from there).
//
// AVATARS ARE VENDORED, NOT HOTLINKED. public/team/chris.png was downloaded
// once from avatars.githubusercontent.com/u/34689321 and committed. Pointing
// <Image> at githubusercontent would make this page depend on GitHub's
// availability AND send every visitor's IP and user-agent to GitHub, which is a
// third-party request nobody asked for on an "own your infrastructure" site. The
// file is a PNG despite what the avatar URL implies — the extension follows the
// bytes (verified with `file`), so Cloudflare Pages serves the right MIME type.
// next.config.mjs sets images.unoptimized (static export), so <Image> emits a
// plain <img> and the explicit width/height are the intrinsic dimensions; the
// h-/w- utilities set the rendered box, giving a 2x-density 112px avatar.
//
// The GitHub API confirms user
// 34689321 is login `chrizefan`, display name "Chris", company "digithings.ai" —
// so the handle, link and avatar belong to the same account. The page limits
// itself to the maintainer role and work visible in the repository; it makes no
// claims about employment history, credentials, or private biography.
type Member = {
  name: string;
  role: string;
  blurb: string;
  /** Local, vendored avatar under public/team/. Never a remote URL. */
  avatar: string;
  /** Intrinsic pixel size of the vendored file (square). */
  avatarSize: number;
  github: string;
  githubHandle: string;
};

const MEMBERS: Member[] = [
  {
    name: "Chris",
    role: "Maintainer",
    blurb:
      "Chris maintains digithings in public. Current code, design decisions, open issues, and " +
      "release history are available in the GitHub repository.",
    avatar: "/team/chris.png",
    avatarSize: 460,
    github: "https://github.com/chrizefan",
    githubHandle: "chrizefan",
  },
];

export default function TeamPage() {
  return (
    <>
      <DtNav />

      <main id="main" tabIndex={-1} className="pt-[var(--dq-nav-h)]">
        <PageHead
          kicker={"// team"}
          title={
            <>
              Meet the <em>maintainer.</em>
            </>
          }
        >
          digithings is currently maintained by Chris. The project is developed in public, so its
          code, decisions, and progress can be reviewed directly.
        </PageHead>

        <section className="section">
          <div className="wrap">
            <span className="kicker">{"// roster"}</span>
            {MEMBERS.map((m) => (
              <div key={m.name} className="mt-[1.2rem] flex flex-wrap items-center gap-[1.2rem]">
                <Image
                  src={m.avatar}
                  alt={`${m.name}, ${m.role.toLowerCase()} of digithings`}
                  width={m.avatarSize}
                  height={m.avatarSize}
                  className="h-[96px] w-[96px] rounded-none border border-hair"
                />
                <div className="grid gap-[0.25rem]">
                  <h2 className="text-[1.1rem] font-normal text-ink">{m.name}</h2>
                  <span className="font-mono text-[0.78rem] text-ink-mute">{m.role}</span>
                  <a
                    className="font-mono text-[0.82rem] text-accent [text-underline-offset:2px] hover:text-ink hover:underline"
                    href={m.github}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    @{m.githubHandle}
                  </a>
                </div>
                <p className="mt-[0.6rem] max-w-[62ch] text-[0.95rem] leading-[1.7] text-ink-soft">
                  {m.blurb}
                </p>
              </div>
            ))}
          </div>
        </section>

        <section className="section section-alt">
          <div className="wrap">
            <span className="kicker">{"// working together"}</span>
            <p className="mt-[0.7rem] max-w-[64ch] text-[1rem] leading-[1.7] text-ink-soft">
              The stack is MIT-licensed and developed in public: issues, pull requests and design
              notes all live in the repository. You can contribute there or contact us for help
              integrating the stack and building on it.
            </p>
            <div className="mt-[1.6rem] flex flex-wrap items-center gap-[0.8rem]">
              <CtaLink href="https://github.com/digithings-ai/digithings" external>
                Contribute on GitHub
              </CtaLink>
              <CtaLink href="/services" variant="ghost">
                View services
              </CtaLink>
              <ContactMailto
                email={DT_CONTACT_EMAIL}
                className="font-mono text-[0.86rem] text-accent [text-underline-offset:2px] hover:text-ink"
                subject="digithings%20inquiry"
                showAddress
              >
                {DT_CONTACT_EMAIL}
              </ContactMailto>
            </div>
          </div>
        </section>
      </main>

      <DtFooter />
    </>
  );
}
