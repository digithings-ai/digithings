import { useEffect, useRef } from "react";
import { Message } from "./Message";
import { ChatMessage, Config } from "../types";

interface WelcomeProps {
  config: Config;
}

function WelcomeScreen({ config }: WelcomeProps) {
  return (
    <div className="flex flex-col items-center justify-center flex-1 gap-5 text-center px-4 animate-[fade-up_0.6s_cubic-bezier(0.2,0.8,0.2,1)_0.1s_both]">
      {/* Logomark */}
      <img src={`${import.meta.env.BASE_URL}qrw.svg`} alt="digithings" className="h-10 w-auto opacity-80" />
      <div>
        <h1 className="text-[1.3rem] font-semibold tracking-[-0.03em] text-[#e6e6e6] mb-1.5">
          {config.title || "Digichat"}
        </h1>
        <p className="text-[0.9rem] text-[#a3a3a3] max-w-xs leading-relaxed">
          Talk to your stack — research, RAG, backtests.
        </p>
      </div>
    </div>
  );
}

interface Props {
  messages: ChatMessage[];
  busy: boolean;
  config: Config;
}

export function MessageList({ messages, config }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div
      className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden pb-4 scroll-smooth [mask-image:linear-gradient(180deg,transparent_0,#000_14px,#000_calc(100%-20px),transparent_100%)]"
      role="log"
      aria-live="polite"
      aria-relevant="additions"
    >
      {messages.length === 0 ? (
        <div className="h-full flex flex-col">
          <WelcomeScreen config={config} />
        </div>
      ) : (
        <div className="flex flex-col gap-5 pt-3">
          {messages.map((msg) => (
            <Message key={msg.id} message={msg} />
          ))}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  );
}
