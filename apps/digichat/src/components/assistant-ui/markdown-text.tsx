"use client";

/**
 * assistant-ui markdown for text (and reasoning) parts.
 * Chart JSON fences are the only digichat override on their code path.
 */
import type { FC } from "react";
import type { SyntaxHighlighterProps } from "@assistant-ui/react-markdown";
import { MarkdownTextPrimitive } from "@assistant-ui/react-markdown";
import remarkGfm from "remark-gfm";
import { EChartsCard } from "@/components/echarts-card";
import { parseChartEnvelope } from "@/lib/chart-spec";

export const JsonChartFence: FC<SyntaxHighlighterProps> = ({
  code,
  components,
}) => {
  const spec = parseChartEnvelope(code);
  if (spec) return <EChartsCard spec={spec} />;
  const Pre = components.Pre;
  const Code = components.Code;
  return (
    <Pre>
      <Code>{code}</Code>
    </Pre>
  );
};

const MARKDOWN_BY_LANGUAGE = {
  json: { SyntaxHighlighter: JsonChartFence },
};

export const MarkdownText: FC = () => (
  <MarkdownTextPrimitive
    remarkPlugins={[remarkGfm]}
    className="aui-md"
    componentsByLanguage={MARKDOWN_BY_LANGUAGE}
  />
);
