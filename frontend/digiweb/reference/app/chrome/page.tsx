import "./chrome.css";
import { AnnouncementBarReference } from "@/components/announcement-bar-reference";
import { CommandPaletteReference } from "@/components/command-palette-reference";
import { FooterReference } from "@/components/footer-reference";
import { ModuleCardReference } from "@/components/chrome/module-card-reference";
import { NavShellReference } from "@/components/chrome/nav-shell-reference";
import { ScrollNavReference } from "@/components/scroll-nav-reference";
import { TabsReference } from "@/components/tabs-reference";
import { ToastStackReference } from "@/components/toast-stack-reference";

export default function ChromePage() {
  return (
    <main className="reference-page">
      <header className="hero">
        <p className="kicker">{"// chrome"}</p>
        <h1>
          Site chrome, <em>quiet by default.</em>
        </h1>
        <p>
          Navigation and footer grammar: scroll-aware bars, utility rows, and the one sanctioned
          personality moment at the very bottom of the page.
        </p>
      </header>

      <AnnouncementBarReference />
      <CommandPaletteReference />
      <TabsReference />
      <ToastStackReference />
      <ScrollNavReference />
      <NavShellReference />
      <ModuleCardReference />
      <FooterReference />
    </main>
  );
}
