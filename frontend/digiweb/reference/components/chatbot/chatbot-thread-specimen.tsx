"use client";

/**
 * Live assistant-ui Thread on the chatbot gallery. Registry Thread plus a
 * local fixture runtime — no custom message tree.
 */
import {
  Thread,
  type ComposerLayout,
  type ThreadComponents,
} from "@/components/assistant-ui/elements/thread.aui";

import { DigichatFixtureRuntime } from "./digichat-fixture-runtime";
import { DigichatThreadWelcome } from "./digichat-thread-welcome";
import {
  GALLERY_PLACEHOLDER,
  GALLERY_SUGGESTIONS,
  GALLERY_WELCOME,
  galleryWelcomeBody,
} from "./digichat-welcome-config";

/** Module-scope so the message tree does not re-render on parent updates. */
export const GALLERY_THREAD_COMPONENTS: ThreadComponents = {
  Welcome: function GalleryWelcome() {
    return (
      <DigichatThreadWelcome
        title={GALLERY_WELCOME.title}
        body={galleryWelcomeBody(GALLERY_WELCOME)}
      />
    );
  },
};

export function ChatbotThreadSpecimen({
  composerLayout = "expanded",
  heading,
  kicker,
  copy,
}: {
  composerLayout?: ComposerLayout;
  heading?: string;
  kicker?: string;
  copy?: string;
}) {
  return (
    <section className="section-block" id={composerLayout === "compact" ? "composer-compact" : "thread"}>
      <p className="kicker">{kicker ?? "// thread"}</p>
      <h2 className="title">{heading ?? "Send a line."}</h2>
      <p className="section-copy">
        {copy ??
          "The fixture streams reasoning, then real MCP tool rows (website: digisearch_query + digivault_get_note; dashboard: digiquant_list_strategies + digiquant_run_backtest), then markdown. Turns use the ChatMessage grammar: both left, cube markers — not bubbles. Copy, regenerate, and attach are the registry actions. Welcome copy sits above the composer; optional example rows come from deploy-shaped config."}
      </p>
      <div
        className="aui-theme-stage"
        data-composer-layout={composerLayout}
      >
        <DigichatFixtureRuntime suggestions={GALLERY_SUGGESTIONS}>
          <Thread
            autoFocus={false}
            components={GALLERY_THREAD_COMPONENTS}
            placeholder={GALLERY_PLACEHOLDER}
            composerLayout={composerLayout}
          />
        </DigichatFixtureRuntime>
      </div>
    </section>
  );
}
