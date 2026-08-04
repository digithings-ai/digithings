import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { Footer, Reveal } from "@digithings/web";
import { DT_CONTACT_EMAIL, DT_FOOTER, DT_FOOTER_META } from "../_nav";
import { PageHead } from "../_company/prose";
import { DtNav } from "@/components/DtNav";

export const metadata: Metadata = {
  title: "team — who builds digithings",
  description:
    "The people behind DigiThings, the open-source modular AI infrastructure stack. Founded and " +
    "maintained in public on GitHub.",
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
// IDENTITY VERIFIED, BIOGRAPHY NOT INVENTED. The GitHub API confirms user
// 34689321 is login `chrizefan`, display name "Chris", company "digithings.ai" —
// so the handle, the link and the avatar belong to the same account. Nothing
// beyond that is asserted: no employers, no credentials, no dates, no prior
// roles, because none of that is in the repository and this page will not make
// it up.
//
// >>> OWNER TO CONFIRM: the `blurb` string below is PLACEHOLDER COPY. It was
// >>> drafted from the repository's own evidence only — the design decisions
// >>> that are visible in the code (MIT licence, self-hosting, per-request
// >>> provider keys, published residual risks) — and from the role the brief
// >>> supplied ("founder"). It is a plausible description of the work, not a
// >>> statement Chris has approved. Replace or approve before launch. The same
// >>> applies to `role`: "Founder" is the title given in the brief; if the
// >>> public-facing title should be different, this is the one place to change
// >>> it.
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
    role: "Founder",
    blurb:
      "Sets the direction of the stack and writes most of it in public. The decisions that shape " +
      "DigiThings are visible in the repository rather than in a pitch: MIT from the first commit, " +
      "self-hosting as the default rather than an enterprise tier, provider keys forwarded per " +
      "request instead of stored, and a threat model that publishes its residual risks alongside " +
      "its controls.",
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

      <main className="pt-[var(--dq-nav-h)]">
        <PageHead
          kicker={"// team"}
          title={
            <>
              Built <em>in the open.</em>
            </>
          }
        >
          A small team, and a repository anyone can read. The work is public commit by commit, so
          the most useful introduction to whoever builds this is the history itself.
        </PageHead>

        <section className="section">
          <div className="wrap">
            {/* The roster needs its own .section-head: without an h2 here the
                member card's h3 would follow the page h1 directly and skip a
                level. It also gives the single card something to sit under
                while the roster is one entry long. */}
            <Reveal className="section-head">
              <span className="kicker">{"// roster"}</span>
              <h2>Who that is.</h2>
            </Reveal>
            <div className="grid gap-[1.1rem] md:grid-cols-2">
              {MEMBERS.map((m) => (
                <Reveal key={m.name} className="mod-card">
                  <div className="flex flex-wrap items-center gap-[1.1rem]">
                    <Image
                      src={m.avatar}
                      alt={`${m.name}, ${m.role.toLowerCase()} of digithings`}
                      width={m.avatarSize}
                      height={m.avatarSize}
                      className="h-[112px] w-[112px] rounded-[14px] border border-hair"
                    />
                    <div className="grid gap-[0.2rem]">
                      <h3>{m.name}</h3>
                      <span className="role">{m.role}</span>
                      <a
                        className="font-mono text-[0.82rem] text-accent [text-underline-offset:2px] hover:text-ink hover:underline"
                        href={m.github}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        @{m.githubHandle}
                      </a>
                    </div>
                  </div>
                  <p className="mt-[1rem] text-[0.92rem] leading-[1.7] text-ink-soft">{m.blurb}</p>
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        <section className="section section-alt">
          <div className="wrap">
            <Reveal className="section-head">
              <span className="kicker">{"// working together"}</span>
              <h2>Contributions and conversations.</h2>
              <p>
                The stack is MIT-licensed and developed in public: issues, pull requests and design
                notes all live in the repository. If you want to build on it with help, that is a
                different conversation and it has its own page.
              </p>
            </Reveal>
            <div className="flex flex-wrap gap-[0.8rem]">
              <a
                className="btn btn-primary"
                href="https://github.com/digithings-ai/digithings"
                target="_blank"
                rel="noopener noreferrer"
              >
                Contribute on GitHub <span aria-hidden="true">→</span>
              </a>
              <Link className="btn btn-ghost" href="/services">
                Work with us
              </Link>
              <a
                className="btn btn-ghost"
                href={`mailto:${DT_CONTACT_EMAIL}?subject=DigiThings%20inquiry`}
              >
                Email
              </a>
            </div>
          </div>
        </section>
      </main>

      <Footer links={DT_FOOTER} meta={DT_FOOTER_META} />
    </>
  );
}
