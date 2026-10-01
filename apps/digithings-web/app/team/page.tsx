import type { Metadata } from "next";
import Image from "next/image";
import {
  ContactMailto,
  CtaLink,
  DocumentFrame,
  GlyphList,
  GlyphRow,
  PageTitle,
  Prose,
  Section,
} from "@digithings/ui";
import { DT_CONTACT_EMAIL } from "@/app/_nav";
import { DtFooter } from "@/components/DtFooter";
import { DtNav } from "@/components/DtNav";

export const metadata: Metadata = {
  title: "team — who builds digithings",
  description:
    "Meet the current maintainer of digithings and follow the project's work in the public " +
    "GitHub repository.",
};

// /team — rebuilt on the document grammar (D1, #4429): one framed column, two
// sections, no roster card grid. One maintainer, kept generic — the page makes
// no claim about employment history, credentials or private biography. The
// avatar is vendored under public/team/, never hotlinked from GitHub, so the
// page sends no third-party request and depends on no external host.

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

const TOGETHER: { label: string; body: string }[] = [
  {
    label: "In the open",
    body:
      "Issues, pull requests and design notes all live in the repository, so the work is readable " +
      "as it happens",
  },
  {
    label: "Get help",
    body:
      "Contribute in the repository, or contact us for help integrating the stack and building " +
      "on it",
  },
];

export default function TeamPage() {
  return (
    <>
      <DtNav />

      <main id="main" tabIndex={-1} className="pt-[var(--dq-nav-h)]">
        <DocumentFrame>
          <div className="px-[var(--page-pad)] py-[var(--page-step)]">
            <PageTitle path="team" title="Meet the maintainer.">
              digithings is maintained by Chris and developed in public, so you can review its
              code, decisions and progress directly.
            </PageTitle>
          </div>

          <Section id="maintainer" title="The maintainer">
            {MEMBERS.map((m) => (
              <div key={m.name}>
                <div className="flex flex-wrap items-center gap-[1.2rem]">
                  <Image
                    src={m.avatar}
                    alt={`${m.name}, ${m.role.toLowerCase()} of digithings`}
                    width={m.avatarSize}
                    height={m.avatarSize}
                    className="h-[96px] w-[96px] border border-hair"
                  />
                  <div className="grid gap-[0.25rem]">
                    <span className="text-[length:var(--type-section)] font-medium text-ink">
                      {m.name}
                    </span>
                    <span className="font-mono text-[length:var(--type-meta)] tracking-[var(--tracking-meta)] uppercase text-ink-mute">
                      {m.role}
                    </span>
                    <a
                      className="font-mono text-[length:var(--type-meta)] text-accent underline-offset-[3px] hover:text-ink hover:underline"
                      href={m.github}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      @{m.githubHandle}
                    </a>
                  </div>
                </div>
                <div className="mt-[1.2rem]">
                  <Prose>
                    <p>{m.blurb}</p>
                  </Prose>
                </div>
              </div>
            ))}
          </Section>

          <Section
            id="working-together"
            title="Working together"
            lede="The stack is MIT-licensed and developed in public, so there are two ways in."
          >
            <GlyphList>
              {TOGETHER.map((r) => (
                <GlyphRow key={r.label} label={r.label}>
                  {r.body}
                </GlyphRow>
              ))}
            </GlyphList>
            <div className="mt-[1.6rem] flex flex-wrap items-center gap-[0.8rem]">
              <CtaLink href="https://github.com/digithings-ai/digithings" external>
                Contribute on GitHub
              </CtaLink>
              <CtaLink href="/services" variant="ghost">
                View services
              </CtaLink>
              <span className="font-mono text-[length:var(--type-body)] text-ink-mute">
                <ContactMailto email={DT_CONTACT_EMAIL} subject="digithings%20inquiry" showAddress>
                  {DT_CONTACT_EMAIL}
                </ContactMailto>
              </span>
            </div>
          </Section>
        </DocumentFrame>
      </main>

      <DtFooter />
    </>
  );
}
