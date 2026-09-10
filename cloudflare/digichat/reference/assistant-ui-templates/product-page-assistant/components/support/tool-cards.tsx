"use client";

import type { IssueAnalysis, SupportSummary } from "@/lib/support/mock-tools";
import { useSupportConfig } from "@/lib/support/config-provider";
import { cn } from "@/lib/utils";
import {
  AlertCircleIcon,
  CheckCircle2Icon,
  ClipboardCheckIcon,
  FileWarningIcon,
  Loader2Icon,
  TicketCheckIcon,
} from "lucide-react";

type ToolStatus = {
  type: "running" | "complete" | "incomplete" | "requires-action";
  reason?: string;
};

type ToolCardProps<TArgs, TResult> = {
  args: TArgs;
  result?: TResult;
  status: ToolStatus;
  toolName?: string;
  displayName?: string;
  expectedRendererType?: string;
};

const statusCopy = (status: ToolStatus, labels: Record<string, string>) => {
  if (status.type === "running") return labels.loading;
  if (status.type === "incomplete" && status.reason === "cancelled") {
    return labels.cancelled;
  }
  if (status.type === "incomplete") return labels.error;
  return labels.success;
};

const CardShell = ({
  title,
  status,
  children,
  icon,
}: {
  title: string;
  status: ToolStatus;
  children: React.ReactNode;
  icon: React.ReactNode;
}) => {
  const { assistant } = useSupportConfig();

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-3 text-sm text-slate-900 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <div className="grid size-8 shrink-0 place-items-center rounded-md bg-[var(--support-accent-soft)] text-[var(--support-accent)]">
            {icon}
          </div>
          <div className="min-w-0">
            <div className="font-medium">{title}</div>
            <div className="text-xs text-slate-500">{statusCopy(status, assistant.labels)}</div>
          </div>
        </div>
        {status.type === "running" ? (
          <Loader2Icon className="mt-1 size-4 animate-spin text-[var(--support-accent)]" />
        ) : status.type === "incomplete" ? (
          <AlertCircleIcon className="mt-1 size-4 text-red-600" />
        ) : (
          <CheckCircle2Icon className="mt-1 size-4 text-emerald-700" />
        )}
      </div>
      <div className="mt-3">{children}</div>
    </section>
  );
};

export function GenericToolCard({
  args,
  result,
  status,
  toolName = "tool",
  displayName,
  expectedRendererType,
}: ToolCardProps<unknown, unknown>) {
  return (
    <CardShell
      title={displayName ?? toolName}
      status={status}
      icon={<ClipboardCheckIcon className="size-4" />}
    >
      {expectedRendererType && (
        <p className="mb-2 text-xs text-slate-500">
          Generic renderer for <span className="font-medium">{expectedRendererType}</span> output.
        </p>
      )}
      <KeyValuePreview label="Input" value={args} />
      {result !== undefined ? (
        <KeyValuePreview label="Output" value={result} />
      ) : (
        <p className="text-xs text-slate-500">Waiting for tool output...</p>
      )}
    </CardShell>
  );
}

export function IssueAnalysisToolCard({
  args,
  result,
  status,
}: ToolCardProps<{ description?: string; attachments?: { name: string }[] }, IssueAnalysis>) {
  const { assistant } = useSupportConfig();

  if (result && !isIssueAnalysis(result)) {
    return (
      <GenericToolCard
        args={args}
        result={result}
        status={status}
        toolName="analyzeIssue"
        displayName={assistant.toolCardLabels.analyzeIssue}
        expectedRendererType="analysis"
      />
    );
  }

  if (!result) {
    return (
      <CardShell
        title={assistant.toolCardLabels.analyzeIssue}
        status={status}
        icon={<FileWarningIcon className="size-4" />}
      >
        <div className="h-2 w-full overflow-hidden rounded bg-slate-100">
          <div className="h-full w-2/3 animate-pulse rounded bg-[var(--support-accent)]" />
        </div>
        <p className="mt-2 text-xs text-slate-500">
          Reviewing description and {args.attachments?.length ?? 0} attachment(s).
        </p>
      </CardShell>
    );
  }

  return (
    <CardShell
      title={assistant.toolCardLabels.analyzeIssue}
      status={status}
      icon={<FileWarningIcon className="size-4" />}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge>{result.category.replaceAll("_", " ")}</Badge>
        <Badge tone={result.severity === "high" ? "red" : "amber"}>
          {result.severity} severity
        </Badge>
        <span className="text-xs text-slate-500">{result.confidence}% confidence</span>
      </div>
      <p className="mt-2 text-slate-700">{result.likelyCause}</p>
      <p className="mt-2 text-xs text-slate-500">
        Affected service: {result.affectedService}. Attachments: {result.attachments.length || 0}.
      </p>
      <p className="mt-2 text-xs text-slate-600">{result.nextStep}</p>
    </CardShell>
  );
}

export function SupportSummaryToolCard({
  result,
  status,
}: ToolCardProps<Record<string, never>, SupportSummary>) {
  const { assistant } = useSupportConfig();

  if (result && !isSupportSummary(result)) {
    return (
      <GenericToolCard
        args={{}}
        result={result}
        status={status}
        toolName="createSupportSummary"
        displayName={assistant.toolCardLabels.createSupportSummary}
        expectedRendererType="summary"
      />
    );
  }

  if (!result) {
    return (
      <CardShell
        title={assistant.toolCardLabels.createSupportSummary}
        status={status}
        icon={<ClipboardCheckIcon className="size-4" />}
      >
        <p className="text-slate-600">Preparing copy-ready support handoff fields...</p>
      </CardShell>
    );
  }

  return (
    <CardShell
      title={assistant.toolCardLabels.createSupportSummary}
      status={status}
      icon={<TicketCheckIcon className="size-4" />}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="brand">{result.ticketId}</Badge>
        <Badge tone={result.priority === "P2" ? "amber" : "emerald"}>
          {result.priority} {assistant.toolData.priorityLabels[result.priority]}
        </Badge>
        <span className="text-xs text-slate-500">{assistant.labels.escalationCta}</span>
      </div>
      <p className="mt-2 font-medium text-slate-900">{result.summary}</p>
      <p className="mt-1 text-slate-700">{result.customerImpact}</p>
      <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
        <Field label="Owner" value={result.recommendedOwner} />
        <Field label="SLA" value={result.nextResponseSla} />
        <Field
          label="Attachments"
          value={result.attachments.length ? result.attachments.join(", ") : "None"}
        />
      </dl>
    </CardShell>
  );
}

const Field = ({ label, value }: { label: string; value: string }) => (
  <div className="rounded-md bg-slate-50 p-2">
    <dt className="text-slate-500">{label}</dt>
    <dd className="mt-1 font-medium text-slate-800">{value}</dd>
  </div>
);

const KeyValuePreview = ({ label, value }: { label: string; value: unknown }) => (
  <div className="mb-2 rounded-md bg-slate-50 p-2">
    <div className="text-xs font-medium text-slate-500">{label}</div>
    <pre className="mt-1 max-h-36 overflow-auto whitespace-pre-wrap break-words text-xs text-slate-700">
      {formatUnknown(value)}
    </pre>
  </div>
);

const formatUnknown = (value: unknown) => {
  if (value === undefined) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null;

const isIssueAnalysis = (value: unknown): value is IssueAnalysis => {
  if (!isRecord(value)) return false;
  return (
    typeof value.category === "string" &&
    typeof value.confidence === "number" &&
    typeof value.likelyCause === "string" &&
    typeof value.affectedService === "string" &&
    typeof value.severity === "string" &&
    typeof value.nextStep === "string" &&
    Array.isArray(value.attachments)
  );
};

const isSupportSummary = (value: unknown): value is SupportSummary => {
  if (!isRecord(value)) return false;
  return (
    typeof value.ticketId === "string" &&
    typeof value.priority === "string" &&
    typeof value.customerImpact === "string" &&
    typeof value.summary === "string" &&
    typeof value.recommendedOwner === "string" &&
    typeof value.nextResponseSla === "string" &&
    Array.isArray(value.attachments)
  );
};

const Badge = ({
  children,
  tone = "slate",
}: {
  children: React.ReactNode;
  tone?: "slate" | "brand" | "emerald" | "amber" | "red";
}) => (
  <span
    className={cn(
      "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium",
      tone === "slate" && "bg-slate-100 text-slate-700",
      tone === "brand" && "bg-[var(--support-accent-soft)] text-[var(--support-accent)]",
      tone === "emerald" && "bg-emerald-100 text-emerald-800",
      tone === "amber" && "bg-amber-100 text-amber-800",
      tone === "red" && "bg-red-100 text-red-800",
    )}
  >
    {children}
  </span>
);
