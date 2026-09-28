import { supportToolData } from "@/lib/support/tool-data";
import type {
  AttachmentMeta,
  IssueAnalysis,
  SupportScenarioId,
  SupportSummary,
  SupportToolData,
} from "@/lib/support/types";

export type { AttachmentMeta, IssueAnalysis, SupportSummary };

const sleep = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    const timeout = setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timeout);
        reject(new DOMException("Cancelled", "AbortError"));
      },
      { once: true },
    );
  });

type SupportScenarioPack = SupportToolData["scenarioPacks"][number];

export const chooseScenario = (
  description: string,
  toolData: SupportToolData = supportToolData,
): SupportScenarioId => {
  const normalized = description.toLowerCase();
  return (
    toolData.scenarioPacks.find((pack) =>
      pack.triggerPhrases.some((phrase) => normalized.includes(phrase)),
    )?.id ?? "sync_failure"
  );
};

const findScenario = (
  scenarioId: SupportScenarioId,
  toolData: SupportToolData = supportToolData,
): SupportScenarioPack =>
  toolData.scenarioPacks.find((pack) => pack.id === scenarioId) ?? toolData.scenarioPacks[0];

export async function analyzeIssue(
  args: {
    description: string;
    attachments?: AttachmentMeta[];
    service?: string;
    scenarioId?: SupportScenarioId;
    toolData?: SupportToolData;
  },
  signal?: AbortSignal,
): Promise<IssueAnalysis> {
  // Real implementation: call your support classification API with the issue
  // description and attachments, then return the normalized analysis object.
  await sleep(220, signal);
  const scenario = findScenario(
    args.scenarioId ?? chooseScenario(args.description, args.toolData),
    args.toolData,
  );

  return {
    category: scenario.analysis.category,
    confidence: scenario.id === "sync_failure" ? 91 : 84,
    likelyCause: scenario.analysis.likelyCause,
    affectedService: args.service ?? scenario.defaultAffectedService,
    severity: scenario.analysis.severity,
    explanation: scenario.analysis.explanation,
    nextStep: scenario.analysis.nextStep,
    followUpQuestions:
      scenario.id === "auth_error"
        ? ["Is this affecting all users or one user?"]
        : ["When did the last successful sync complete?"],
    attachments: args.attachments ?? [],
  };
}

export async function createSupportSummary(
  args: {
    issue: IssueAnalysis;
    attachments?: AttachmentMeta[];
    scenarioId?: SupportScenarioId;
    toolData?: SupportToolData;
  },
  signal?: AbortSignal,
): Promise<SupportSummary> {
  // Real implementation: create a ticket or handoff in your support system,
  // then return the normalized summary fields for the UI card.
  await sleep(180, signal);
  const scenario = findScenario(
    args.scenarioId ?? (args.issue.category === "unknown" ? "sync_failure" : args.issue.category),
    args.toolData,
  );
  const attachments = (args.attachments ?? args.issue.attachments).map(
    (attachment) => attachment.name,
  );

  return {
    ticketId: scenario.summary.ticketId,
    priority: scenario.summary.priority,
    customerImpact: scenario.summary.customerImpact,
    summary: `${args.issue.affectedService}: ${args.issue.likelyCause}`,
    recommendedOwner: scenario.summary.recommendedOwner,
    nextResponseSla: scenario.summary.nextResponseSla,
    attachments,
  };
}
