"use client";

/**
 * Chrome specimens: desk (list + compact thread) and contained launcher.
 * Thread and launcher are chat subpaths — not the @digithings/web barrel.
 */
import { useAui } from "@assistant-ui/react";
import { DigichatLauncher } from "@digithings/web/chat/launcher";
import { Thread } from "@digithings/web/chat/thread";
import { ChatbotThreadList } from "./chatbot-thread-list";
import { GALLERY_THREAD_COMPONENTS } from "./chatbot-thread-specimen";
import { DigichatFixtureRuntime } from "./digichat-fixture-runtime";
import { GALLERY_PLACEHOLDER, GALLERY_SUGGESTIONS } from "./digichat-welcome-config";

function GalleryLauncher() {
  const aui = useAui();
  return (
    <DigichatLauncher
      portal={false}
      title="digichat"
      onNewChat={() => aui.threads.switchToNewThread()}
    >
      <Thread
        autoFocus={false}
        components={GALLERY_THREAD_COMPONENTS}
        placeholder={GALLERY_PLACEHOLDER}
        composerLayout="compact"
      />
    </DigichatLauncher>
  );
}

export function ChatbotChromeSpecimen() {
  return (
    <>
      <section className="section-block" id="chrome">
        <p className="kicker">{"// chrome"}</p>
        <h2 className="title">Desk.</h2>
        <p className="section-copy">
          Terminal nav on the left, compact Thread on the right.{" "}
          New chat starts another conversation. The list is not a
          ChatGPT rail — <code>digichat</code> label, title only, hairline only.
        </p>
        <div
          className="aui-theme-stage aui-chrome-desk"
          data-composer-layout="compact"
        >
          <DigichatFixtureRuntime suggestions={GALLERY_SUGGESTIONS}>
            <div className="aui-chrome-desk-split">
              <ChatbotThreadList />
              <Thread
                autoFocus={false}
                components={GALLERY_THREAD_COMPONENTS}
                placeholder={GALLERY_PLACEHOLDER}
                composerLayout="compact"
              />
            </div>
          </DigichatFixtureRuntime>
        </div>
      </section>
      <section className="section-block" id="launcher">
        <p className="kicker">{"// launcher"}</p>
        <h2 className="title">Embed.</h2>
        <p className="section-copy">
          Contained <code>DigichatLauncher</code> — 30px square, types{" "}
          <code>digichat</code> on hover, two-step expand. Not a live page
          corner. Solid canvas, no glass.
        </p>
        <div
          className="aui-theme-stage aui-chrome-launcher-stage"
          data-composer-layout="compact"
        >
          <DigichatFixtureRuntime suggestions={GALLERY_SUGGESTIONS}>
            <GalleryLauncher />
          </DigichatFixtureRuntime>
        </div>
      </section>
    </>
  );
}
