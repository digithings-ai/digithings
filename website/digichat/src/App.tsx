import { StarField } from "./components/StarField";
import { TopBar } from "./components/TopBar";
import { MessageList } from "./components/MessageList";
import { Composer } from "./components/Composer";
import { useConfig } from "./hooks/useConfig";
import { useHealth } from "./hooks/useHealth";
import { useChat } from "./hooks/useChat";

export function App() {
  const { config, ready } = useConfig();
  const { health } = useHealth(config.digigraphUrl, ready);
  const { messages, busy, sendMessage, abort, newSession } = useChat(config);

  return (
    <>
      {/* Solid black base for Safari */}
      <div className="fixed inset-0 -z-20 bg-black" aria-hidden="true" />
      <StarField />

      <div className="h-full flex flex-col max-w-[900px] mx-auto px-4">
        <TopBar config={config} health={health} onNewChat={newSession} />
        <MessageList messages={messages} busy={busy} config={config} />
        <Composer onSend={sendMessage} onAbort={abort} busy={busy} />
      </div>
    </>
  );
}
