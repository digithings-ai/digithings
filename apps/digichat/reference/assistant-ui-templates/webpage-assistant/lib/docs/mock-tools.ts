import type {
  DemoFlowId,
  DocsAssistantConfig,
  DocsPage,
  GenerateCodeSnippetOutput,
  OpenPageOutput,
  SearchDocsOutput,
} from "@/lib/docs/types";

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

export function getPageById(pageId: string | undefined, pages: DocsPage[], defaultPageId?: string) {
  return (
    pages.find((page) => page.id === pageId) ??
    pages.find((page) => page.id === defaultPageId) ??
    pages[0]
  );
}

export function chooseDemoFlow({
  message,
  assistant,
}: {
  message: string;
  assistant: DocsAssistantConfig;
}): DemoFlowId | "currentPage" {
  const normalized = message.toLowerCase();

  const exactPrompt = assistant.suggestedPrompts.find((prompt) =>
    [prompt.title, prompt.prompt].some(
      (value) => value !== undefined && value.toLowerCase() === normalized,
    ),
  );
  if (exactPrompt?.flowId) return exactPrompt.flowId;

  for (const [flowId, flow] of Object.entries(assistant.demoFlows) as Array<
    [DemoFlowId, { triggerPhrases: string[] }]
  >) {
    if (flow.triggerPhrases.some((phrase) => normalized.includes(phrase.toLowerCase()))) {
      return flowId;
    }
  }

  if (normalized.includes("page") || normalized.includes("where am i")) return "currentPage";
  return "auth401";
}

export async function searchDocs(
  args: { query: string; limit?: number; pages: DocsPage[] },
  signal?: AbortSignal,
): Promise<SearchDocsOutput> {
  await sleep(120, signal);
  const terms = args.query
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter(Boolean);

  const results = args.pages
    .map((page) => {
      const haystack = [
        page.id,
        page.title,
        page.section,
        page.description,
        page.keywords.join(" "),
        page.markdown,
      ]
        .join(" ")
        .toLowerCase();
      const matches = terms.filter((term) => haystack.includes(term));
      const score = matches.length * 24 + (haystack.includes(args.query.toLowerCase()) ? 15 : 0);
      return {
        pageId: page.id,
        title: page.title,
        section: page.section,
        url: page.url,
        snippet: page.description,
        score,
      };
    })
    .filter((result) => result.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, args.limit ?? 3);

  return {
    query: args.query,
    results:
      results.length > 0
        ? results
        : args.pages.slice(0, args.limit ?? 3).map((page, index) => ({
            pageId: page.id,
            title: page.title,
            section: page.section,
            url: page.url,
            snippet: page.description,
            score: 30 - index,
          })),
  };
}

export async function openPage(
  args: { pageId: string; pages: DocsPage[]; defaultPageId?: string },
  signal?: AbortSignal,
): Promise<OpenPageOutput> {
  await sleep(90, signal);
  const page = getPageById(args.pageId, args.pages, args.defaultPageId);

  return {
    pageId: page.id,
    title: page.title,
    section: page.section,
    url: page.url,
    description: page.description,
    relatedPageIds: page.relatedPageIds,
  };
}

export async function generateCodeSnippet(
  args: {
    topic: string;
    language?: "curl" | "typescript" | "python";
  },
  signal?: AbortSignal,
): Promise<GenerateCodeSnippetOutput> {
  await sleep(100, signal);
  const language = args.language ?? "typescript";

  return {
    topic: args.topic,
    language,
    code:
      language === "curl"
        ? 'curl https://api.example.com/v1/resource \\\n  -H "Authorization: Bearer $API_KEY"'
        : 'const response = await fetch("https://api.example.com/v1/resource");',
    notes: ["Replace this mock implementation with your snippet source."],
    docsUrl: "/docs/quickstart",
  };
}
