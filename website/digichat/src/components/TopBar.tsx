import { useState } from "react";
import { StatusPill } from "./StatusPill";
import { HealthState, Config } from "../types";

interface Props {
  config: Config;
  health: HealthState;
  onNewChat: () => void;
}

export function TopBar({ config, health, onNewChat }: Props) {
  const [showHelp, setShowHelp] = useState(false);

  return (
    <header className="flex-shrink-0 flex items-center justify-between gap-4 px-0 py-3 border-b border-[#2a2a2a] bg-gradient-to-b from-[rgba(10,10,10,0.95)] to-[rgba(10,10,10,0.75)] backdrop-blur-md animate-[bar-in_0.5s_cubic-bezier(0.2,0.8,0.2,1)_both]">
      {/* Brand */}
      <a
        className="flex items-center gap-2.5 no-underline text-inherit"
        href="../"
        title="digithings"
      >
        <img src={`${import.meta.env.BASE_URL}qrw.svg`} alt="digithings" height={24} className="h-6 w-auto shrink-0" />
        <div className="flex flex-col gap-0.5">
          <strong className="font-semibold text-[0.92rem] tracking-[-0.02em] text-[#e6e6e6]">
            {config.title || "Digichat"}
          </strong>
          <span className="text-[0.7rem] text-[#a3a3a3] hidden sm:block">
            {config.subtitle || "DigiGraph"}
          </span>
        </div>
      </a>

      {/* Right actions */}
      <div className="flex items-center gap-2">
        <StatusPill health={health} digigraphUrl={config.digigraphUrl} className="hidden sm:inline-flex" />

        {/* Help toggle */}
        <div className="relative">
          <button
            type="button"
            onClick={() => setShowHelp((v) => !v)}
            className="w-7 h-7 rounded-full flex items-center justify-center text-[#a3a3a3] border border-[#2a2a2a] bg-white/[0.04] hover:bg-white/[0.08] hover:text-[#e6e6e6] transition-colors text-[0.7rem] font-medium cursor-pointer"
            aria-label="Setup instructions"
          >
            ?
          </button>
          {showHelp && (
            <div className="absolute right-0 top-9 z-50 w-72 p-3.5 rounded-xl border border-[#2a2a2a] bg-[#0a0a0a]/95 backdrop-blur-md text-[0.78rem] text-[#a3a3a3] leading-relaxed shadow-xl animate-[fade-up_0.2s_cubic-bezier(0.2,0.8,0.2,1)_both]">
              <p className="text-[#e6e6e6] font-medium mb-1.5">Setup</p>
              <p>
                Copy{" "}
                <code className="font-mono text-[0.75rem] bg-white/[0.06] px-1 py-0.5 rounded">
                  config.example.json
                </code>{" "}
                →{" "}
                <code className="font-mono text-[0.75rem] bg-white/[0.06] px-1 py-0.5 rounded">
                  config.json
                </code>{" "}
                and set your DigiGraph URL.
              </p>
              <p className="mt-1.5">
                Current endpoint:{" "}
                <code className="font-mono text-[0.75rem] text-[#4a90e2] break-all">
                  {config.digigraphUrl}
                </code>
              </p>
            </div>
          )}
        </div>

        <button
          type="button"
          onClick={onNewChat}
          className="text-[0.78rem] font-medium text-[#e6e6e6] bg-white/[0.06] border border-[#2a2a2a] rounded-lg px-3 py-1.5 hover:bg-white/[0.1] hover:border-white/20 active:scale-[0.98] transition-all cursor-pointer"
        >
          New chat
        </button>
      </div>
    </header>
  );
}
