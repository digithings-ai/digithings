import "./chrome.css";
import { AnnouncementBarReference } from "@/components/announcement-bar-reference";
import { FooterReference } from "@/components/footer-reference";
import { ScrollNavReference } from "@/components/scroll-nav-reference";

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
      <ScrollNavReference />
      <FooterReference />
    </main>
  );
}
