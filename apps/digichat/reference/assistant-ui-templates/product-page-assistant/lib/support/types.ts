import type { z } from "zod";

export type SupportScenarioId = "sync_failure" | "auth_error";

export type BuiltInSupportToolId = "analyzeIssue" | "createSupportSummary";

export type SupportToolId = BuiltInSupportToolId | (string & {});

export type SupportToolRenderer = "analysis" | "summary" | "generic";

export type BrandTheme = {
  accent: string;
  surface: string;
  border: string;
  mutedText: string;
  success: string;
  warning: string;
  destructive: string;
  focusRing: string;
};

export type AttachmentMeta = {
  name: string;
  type?: string;
};

export type IssueAnalysis = {
  category: SupportScenarioId | "unknown";
  confidence: number;
  likelyCause: string;
  affectedService: string;
  severity: "low" | "medium" | "high";
  explanation: string;
  nextStep: string;
  followUpQuestions: string[];
  attachments: AttachmentMeta[];
};

export type SupportSummary = {
  ticketId: string;
  priority: "P1" | "P2" | "P3";
  customerImpact: string;
  summary: string;
  recommendedOwner: string;
  nextResponseSla: string;
  attachments: string[];
};

export type AnalyzeIssueInput = {
  description: string;
  service: string;
  attachments: AttachmentMeta[];
  scenarioId: SupportScenarioId;
};

export type CreateSupportSummaryInput = {
  issue: IssueAnalysis;
  attachments: AttachmentMeta[];
  scenarioId: SupportScenarioId;
};

export type AnalyzeIssueDemoFlowStep = {
  id: string;
  toolId: "analyzeIssue";
  assistantText: string;
  input: AnalyzeIssueInput;
  output: IssueAnalysis;
};

export type CreateSupportSummaryDemoFlowStep = {
  id: string;
  toolId: "createSupportSummary";
  assistantText: string;
  input: CreateSupportSummaryInput;
  output: SupportSummary;
};

export type DemoFlowStep =
  | AnalyzeIssueDemoFlowStep
  | CreateSupportSummaryDemoFlowStep
  | {
      id: string;
      toolId: SupportToolId;
      assistantText: string;
      input: unknown;
      output: unknown;
    };

export type SupportAssistantConfig = {
  companyName: string;
  productName: string;
  assistantName: string;
  welcome: {
    badge: string;
    title: string;
    subtitle: string;
  };
  labels: {
    modalTrigger: string;
    modalClose: string;
    composerPlaceholder: string;
    composerInput: string;
    uploadButton: string;
    send: string;
    cancel: string;
    copy: string;
    refresh: string;
    more: string;
    edit: string;
    previous: string;
    next: string;
    scrollToBottom: string;
    export: string;
    escalationCta: string;
    loading: string;
    success: string;
    error: string;
    cancelled: string;
  };
  agentPrompt: {
    persona: string;
    instructions: string;
    responseStyle: string;
  };
  demoModeNotice: string;
  suggestedPrompts: Array<{
    title: string;
    label: string;
    prompt: string;
    scenarioId: SupportScenarioId;
  }>;
  tools: Array<{
    id: SupportToolId;
    displayName: string;
    aiDescription: string;
    realImplementationHint: string;
    rendererType: SupportToolRenderer;
    inputSchema?: Record<string, unknown>;
    outputSchema?: Record<string, unknown>;
    mockResponse?: unknown;
  }>;
  demoFlows: Record<
    SupportScenarioId,
    {
      finalResponse: string;
      steps: DemoFlowStep[];
    }
  >;
  toolData: SupportToolData;
  toolCardLabels: Record<string, string>;
  toolCardDesign: Record<string, string>;
};

export type SupportScenarioPack = {
  id: SupportScenarioId;
  title: string;
  triggerPhrases: string[];
  defaultAffectedService: string;
  mockAttachments: string[];
  firstResponse: string;
  analysis: {
    category: SupportScenarioId;
    likelyCause: string;
    severity: "low" | "medium" | "high";
    explanation: string;
    nextStep: string;
  };
  summary: {
    ticketId: string;
    priority: "P1" | "P2" | "P3";
    customerImpact: string;
    recommendedOwner: string;
    nextResponseSla: string;
  };
};

export type SupportToolData = {
  serviceOptions: string[];
  mockAccountStatus: {
    accountName: string;
    plan: string;
    region: string;
    accountHealth: string;
  };
  escalationLabels: Record<string, string>;
  priorityLabels: Record<"P1" | "P2" | "P3", string>;
  scenarioPacks: SupportScenarioPack[];
};

export type SupportToolParameterSchema = z.ZodTypeAny;
