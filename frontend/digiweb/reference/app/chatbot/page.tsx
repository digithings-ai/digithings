import "./chatbot.css";
import { ChatComposerReference } from "@/components/chatbot/chat-composer-reference";
import { ChatInlineChartReference } from "@/components/chatbot/chat-inline-chart-reference";
import { ChatInlineGraphReference } from "@/components/chatbot/chat-inline-graph-reference";
import { ChatMarkdownReference } from "@/components/chatbot/chat-markdown-reference";
import { ChatThinkingReference } from "@/components/chatbot/chat-thinking-reference";
import { ChatToolCallReference } from "@/components/chatbot/chat-toolcall-reference";
import { ChatWidgetsReference } from "@/components/chatbot/chat-widgets-reference";

export default function ChatbotPage() {
  return (
    <main className="reference-page accent-digichat">
      <header className="hero">
        <p className="kicker">{"// chatbot"}</p>
        <h1>
          The chat surface, <em>rendered.</em>
        </h1>
        <p>
          digichat is a terminal, inhabited — the builder-first CLI register of Claude Code,
          opencode and grok, but with the modern affordances a graph needs: a mono scrollback with a{" "}
          <code>&gt;</code> prompt, collapsible tool-call blocks, and rendered objects (markdown,
          charts, graphs, action widgets) embedded right in the output. Clear, dense, easy to get
          used to. Every turn wears the digichat rose; money and code colors stay quarantined.
        </p>
      </header>

      <ChatThinkingReference />
      <ChatToolCallReference />
      <ChatComposerReference />
      <ChatMarkdownReference />
      <ChatInlineChartReference />
      <ChatInlineGraphReference />
      <ChatWidgetsReference />
    </main>
  );
}
