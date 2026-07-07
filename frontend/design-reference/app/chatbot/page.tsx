import "./chatbot.css";
import { ChatComposerReference } from "@/components/chatbot/chat-composer-reference";
import { ChatInlineChartReference } from "@/components/chatbot/chat-inline-chart-reference";
import { ChatInlineGraphReference } from "@/components/chatbot/chat-inline-graph-reference";
import { ChatMarkdownReference } from "@/components/chatbot/chat-markdown-reference";
import { ChatThinkingReference } from "@/components/chatbot/chat-thinking-reference";
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
          digichat is the terminal, inhabited — a conversation that can think out loud, render
          markdown, draw its own charts and graphs, and hand you widgets you can act on. Every
          turn wears the rose livery; money and code colors stay quarantined to where they mean
          something.
        </p>
      </header>

      <ChatThinkingReference />
      <ChatComposerReference />
      <ChatMarkdownReference />
      <ChatInlineChartReference />
      <ChatInlineGraphReference />
      <ChatWidgetsReference />
    </main>
  );
}
