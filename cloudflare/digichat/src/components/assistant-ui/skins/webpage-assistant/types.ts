export type BuiltInDocsToolId = "searchDocs" | "openPage" | "generateCodeSnippet";

export type DocsToolId = BuiltInDocsToolId | (string & {});

export type DocsToolRenderer = "sourceResults" | "pagePreview" | "codeSnippet" | "generic";

export type DemoFlowId = "auth401" | "webhooks" | "codeExample";

export type SuggestedPrompt = {
  title: string;
  description?: string;
  prompt?: string;
  flowId?: DemoFlowId;
};

export type DocsToolConfig = {
  id: DocsToolId;
  displayName: string;
  aiDescription: string;
  realImplementationHint: string;
  rendererType: DocsToolRenderer;
  inputSchema?: Record<string, unknown>;
  outputSchema?: Record<string, unknown>;
  mockResponse?: unknown;
};

export type DocsPage = {
  id: string;
  title: string;
  section: string;
  description: string;
  url: string;
  markdown: string;
  keywords: string[];
  relatedPageIds: string[];
};

export type CodeSnippet = {
  topic: string;
  language: "curl" | "typescript" | "python";
  code: string;
  notes: string[];
  docsUrl: string;
};

export type SearchResult = {
  pageId: string;
  title: string;
  section: string;
  url: string;
  snippet: string;
  score: number;
};

export type SearchDocsOutput = {
  query: string;
  results: SearchResult[];
};

export type OpenPageOutput = {
  pageId: string;
  title: string;
  section: string;
  url: string;
  description: string;
  relatedPageIds: string[];
};

export type GenerateCodeSnippetOutput = CodeSnippet;

export type DocsToolInputById = {
  searchDocs: { query: string; limit?: number };
  openPage: { pageId: string };
  generateCodeSnippet: { topic: string; language?: "curl" | "typescript" | "python" };
};

export type DocsToolOutputById = {
  searchDocs: SearchDocsOutput;
  openPage: OpenPageOutput;
  generateCodeSnippet: GenerateCodeSnippetOutput;
};

export type SearchDocsDemoFlowStep = {
  id: string;
  assistantText: string;
  toolId: "searchDocs";
  input: DocsToolInputById["searchDocs"];
  output: DocsToolOutputById["searchDocs"];
};

export type OpenPageDemoFlowStep = {
  id: string;
  assistantText: string;
  toolId: "openPage";
  input: DocsToolInputById["openPage"];
  output: DocsToolOutputById["openPage"];
};

export type GenerateCodeSnippetDemoFlowStep = {
  id: string;
  assistantText: string;
  toolId: "generateCodeSnippet";
  input: DocsToolInputById["generateCodeSnippet"];
  output: DocsToolOutputById["generateCodeSnippet"];
};

export type DemoFlowStep =
  | SearchDocsDemoFlowStep
  | OpenPageDemoFlowStep
  | GenerateCodeSnippetDemoFlowStep
  | {
      id: string;
      assistantText: string;
      toolId: DocsToolId;
      input: unknown;
      output: unknown;
    };

export type DemoFlowConfig = {
  triggerPhrases: string[];
  title: string;
  steps: DemoFlowStep[];
  finalResponse: string;
};

export type DocsAssistantConfig = {
  productName: string;
  docsName: string;
  assistantName: string;
  welcome: {
    headline: string;
    body: string;
  };
  labels: {
    currentPage: string;
    source: string;
    relatedPages: string;
    openPage: string;
    headerSearch: string;
    articleCtaTitle: string;
    articleCtaBody: string;
    articleCtaAction: string;
    composerPlaceholder: string;
    previewWarning: string;
  };
  suggestedPrompts: SuggestedPrompt[];
  tools: DocsToolConfig[];
  demoModeNotice: string;
  demoFlows: Record<DemoFlowId, DemoFlowConfig>;
};

export type BrandTheme = {
  accent: string;
  surface: string;
  border: string;
  mutedText: string;
  focusRing: string;
};

export type DocsNavGroup = {
  label: string;
  pageIds: string[];
};

export type DocsHostUiSpec = {
  version: 1;
  root: {
    type: "ContentShell";
    props: {
      productName: string;
      docsName: string;
      defaultPageId: string;
      pages: DocsPage[];
      assistantPlacement?: "sidebar" | "modal";
      navGroups?: DocsNavGroup[];
    };
  };
};
