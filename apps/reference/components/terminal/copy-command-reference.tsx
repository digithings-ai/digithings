"use client";

/**
 * Copy command — the install line is the button. A click blurs the command
 * and shows "copied". The hero clone and the module compose line are this
 * same control.
 */
import { CopyCommand } from "@digithings/ui";

export function CopyCommandReference() {
  return (
    <section className="section-block" id="copy-command">
      <p className="kicker">{"// copy command"}</p>
      <h2 className="title">The command is the button.</h2>
      <p className="section-copy">
        <code>CopyCommand</code> from <code>@digithings/ui</code>. There is no separate copy
        control: the line itself copies. A click blurs the command and shows copied, then the
        command returns. The digithings.ai hero clone and the module mosaic compose line are this
        same button.
      </p>
      <div className="mt-[1.2rem] flex max-w-full flex-col items-start gap-[0.65rem]">
        <CopyCommand
          inline
          ariaLabel="Clone command"
          samples={[
            {
              label: "clone",
              protocol: "git clone",
              code: "git clone https://github.com/digithings-ai/digithings",
            },
          ]}
        />
        <CopyCommand
          inline
          ariaLabel="Compose command"
          samples={[
            {
              label: "compose",
              protocol: "docker compose",
              code: "docker compose up -d digiquant",
            },
          ]}
        />
      </div>
    </section>
  );
}
