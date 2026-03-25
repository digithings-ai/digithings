import { HealthState } from "../types";

interface Props {
  health: HealthState;
  digigraphUrl: string;
  className?: string;
}

const STATE_LABEL: Record<HealthState, string> = {
  unknown: "Checking…",
  ok: "DigiGraph up",
  err: "Unreachable",
};

const DOT_CLASS: Record<HealthState, string> = {
  unknown: "bg-[#555]",
  ok: "bg-[#27c93f] shadow-[0_0_10px_rgba(39,201,63,0.5)]",
  err: "bg-[#ff5f56] shadow-[0_0_10px_rgba(255,95,86,0.5)]",
};

export function StatusPill({ health, digigraphUrl, className = "" }: Props) {
  return (
    <div
      className={`inline-flex items-center gap-1.5 text-[0.72rem] text-[#a3a3a3] px-2.5 py-1.5 rounded-full border border-[#2a2a2a] bg-white/[0.03] ${className}`}
      title={`DigiGraph: ${digigraphUrl}/health`}
    >
      <span
        className={`w-[7px] h-[7px] rounded-full shrink-0 transition-all duration-300 ${DOT_CLASS[health]}`}
        aria-hidden="true"
      />
      <span>{STATE_LABEL[health]}</span>
    </div>
  );
}
