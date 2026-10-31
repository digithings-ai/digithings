"use client";

import "@assistant-ui/react-markdown/styles/dot.css";

import {
  type CodeHeaderProps,
  MarkdownTextPrimitive,
  unstable_memoizeMarkdownComponents as memoizeMarkdownComponents,
  useIsMarkdownCodeBlock,
} from "@assistant-ui/react-markdown";
import remarkGfm from "remark-gfm";
import { isFollowableHref } from "../followable-href";
import { remarkStripModelBoilerplate } from "../strip-model-boilerplate";
import { type FC, memo, useMemo, useRef } from "react";
import type { TextMessagePartProps } from "@assistant-ui/react";
import { CheckIcon, CopyIcon } from "lucide-react";

import { TooltipIconButton } from "./tooltip-icon-button";
import { useCopyToClipboard } from "./use-copy-to-clipboard";
import { ArtifactLink, isArtifactBlobHref } from "./artifacts-panel";
import { cn } from "@/lib/utils";
import { stockRadius, useStockShape } from "./stock-shape";

type MarkdownTextProps = Partial<TextMessagePartProps> & {
  components?: Parameters<typeof memoizeMarkdownComponents>[0];
};

const useShallowStable = <T extends Record<string, unknown> | undefined>(
  value: T,
): T => {
  const ref = useRef(value);
  if (value !== ref.current) {
    const prev = ref.current;
    const stable =
      value !== undefined &&
      prev !== undefined &&
      Object.keys(prev).length === Object.keys(value).length &&
      Object.keys(value).every((key) => prev[key] === value[key]);
    if (!stable) ref.current = value;
  }
  return ref.current;
};

const MarkdownTextImpl: FC<MarkdownTextProps> = ({ components }) => {
  const stableComponents = useShallowStable(components);
    const markdownComponents = useMemo(() => {
    if (!stableComponents) return defaultComponents;
    return {
      ...defaultComponents,
      ...memoizeMarkdownComponents(stableComponents),
    };
  }, [stableComponents]);

  return (
    <MarkdownTextPrimitive
      remarkPlugins={[remarkGfm, remarkStripModelBoilerplate]}
      className="aui-md"
      components={markdownComponents}
      defer
    />
  );
};

export const MarkdownText = memo(MarkdownTextImpl);

const CodeHeader: FC<CodeHeaderProps> = ({ language, code }) => {
  const { isCopied, copyToClipboard } = useCopyToClipboard();
  const onCopy = () => {
    if (!code || isCopied) return;
    copyToClipboard(code);
  };

  const stock = useStockShape();

  return (
    <div
      className={cn(
        "aui-code-header-root border-hair bg-surface-2/50 mt-3 flex items-center justify-between border border-b-0 px-3.5 py-1.5 text-xs",
        stockRadius(stock, "rounded-t-xl"),
      )}
    >
      <span className="aui-code-header-language text-ink-mute font-medium lowercase">
        {language}
      </span>
      <TooltipIconButton tooltip="Copy" onClick={onCopy}>
        {!isCopied && (
          <CopyIcon className="animate-in zoom-in-75 fade-in duration-(--dur-fast)" />
        )}
        {isCopied && (
          <CheckIcon className="animate-in zoom-in-50 fade-in duration-(--duration-hover) ease-out" />
        )}
      </TooltipIconButton>
    </div>
  );
};

// Exported so the `a:` override's routing is testable: without a pin, a
// revert to the plain anchor would pass every suite that only exercises
// ArtifactLink directly.
export const defaultComponents = memoizeMarkdownComponents({
  h1: ({ className, ...props }) => (
    <h1
      className={cn(
        "aui-md-h1 mt-5 mb-2 scroll-m-20 text-xl font-semibold first:mt-0 last:mb-0",
        className,
      )}
      {...props}
    />
  ),
  h2: ({ className, ...props }) => (
    <h2
      className={cn(
        "aui-md-h2 mt-5 mb-2 scroll-m-20 text-lg font-semibold first:mt-0 last:mb-0",
        className,
      )}
      {...props}
    />
  ),
  h3: ({ className, ...props }) => (
    <h3
      className={cn(
        "aui-md-h3 mt-4 mb-1.5 scroll-m-20 text-base font-semibold first:mt-0 last:mb-0",
        className,
      )}
      {...props}
    />
  ),
  h4: ({ className, ...props }) => (
    <h4
      className={cn(
        "aui-md-h4 mt-3.5 mb-1 scroll-m-20 text-base font-medium first:mt-0 last:mb-0",
        className,
      )}
      {...props}
    />
  ),
  h5: ({ className, ...props }) => (
    <h5
      className={cn(
        "aui-md-h5 mt-3 mb-1 text-sm font-semibold first:mt-0 last:mb-0",
        className,
      )}
      {...props}
    />
  ),
  h6: ({ className, ...props }) => (
    <h6
      className={cn(
        "aui-md-h6 mt-3 mb-1 text-sm font-medium first:mt-0 last:mb-0",
        className,
      )}
      {...props}
    />
  ),
  p: ({ className, ...props }) => (
    <p
      className={cn(
        "aui-md-p my-3 leading-relaxed first:mt-0 last:mb-0",
        className,
      )}
      {...props}
    />
  ),
  // A citation to a non-web source (repo://, vault paths) arrives with its href
  // emptied by the sanitizer; an <a href=""> would reload the embed itself
  // (carrying its query string). Show the label as plain text instead.
  a: ({ className, href, children, ...props }) =>
    !isFollowableHref(href) ? (
      <span className="aui-md-a-plain">{children}</span>
    ) : isArtifactBlobHref(href) ? (
      <ArtifactLink href={href as string} className={className}>
        {children}
      </ArtifactLink>
    ) : (
      <a
        className={cn(
          "aui-md-a text-accent hover:text-accent/80 underline underline-offset-2",
          className,
        )}
        href={href}
        {...props}
      >
        {children}
      </a>
    ),
  blockquote: ({ className, ...props }) => (
    <blockquote
      className={cn(
        "aui-md-blockquote border-hair-2 text-ink-mute my-3 border-s-2 ps-4",
        className,
      )}
      {...props}
    />
  ),
  ul: ({ className, ...props }) => (
    <ul
      className={cn(
        "aui-md-ul marker:text-ink-mute my-3 ms-5 list-disc [&>li]:mt-1",
        className,
      )}
      {...props}
    />
  ),
  ol: ({ className, ...props }) => (
    <ol
      className={cn(
        "aui-md-ol marker:text-ink-mute my-3 ms-5 list-decimal [&>li]:mt-1",
        className,
      )}
      {...props}
    />
  ),
  hr: ({ className, ...props }) => (
    <hr
      className={cn("aui-md-hr border-hair my-3", className)}
      {...props}
    />
  ),
  table: ({ className, ...props }) => (
    <div className="aui-md-table-wrapper my-3 overflow-x-auto">
      <table
        className={cn(
          "aui-md-table w-full border-separate border-spacing-0",
          className,
        )}
        {...props}
      />
    </div>
  ),
  th: function Th({ className, ...props }) {
    const stock = useStockShape();
    return (
      <th
        className={cn(
          "aui-md-th bg-surface-2 px-3 py-1.5 text-start font-medium [[align=center]]:text-center [[align=right]]:text-right",
          stockRadius(
            stock,
            "first:rounded-ss-lg last:rounded-se-lg",
            "first:rounded-none last:rounded-none",
          ),
          className,
        )}
        {...props}
      />
    );
  },
  td: ({ className, ...props }) => (
    <td
      className={cn(
        "aui-md-td border-hair border-s border-b px-3 py-1.5 text-start last:border-e [[align=center]]:text-center [[align=right]]:text-right",
        className,
      )}
      {...props}
    />
  ),
  tr: function Tr({ className, ...props }) {
    const stock = useStockShape();
    return (
      <tr
        className={cn(
          "aui-md-tr m-0 border-b p-0 first:border-t",
          stockRadius(
            stock,
            "[&:last-child>td:first-child]:rounded-es-lg [&:last-child>td:last-child]:rounded-ee-lg",
            "[&:last-child>td:first-child]:rounded-none [&:last-child>td:last-child]:rounded-none",
          ),
          className,
        )}
        {...props}
      />
    );
  },
  li: ({ className, ...props }) => (
    <li className={cn("aui-md-li leading-relaxed", className)} {...props} />
  ),
  strong: ({ className, ...props }) => (
    <strong
      className={cn("aui-md-strong font-semibold", className)}
      {...props}
    />
  ),
  sup: ({ className, ...props }) => (
    <sup
      className={cn("aui-md-sup [&>a]:text-xs [&>a]:no-underline", className)}
      {...props}
    />
  ),
  pre: function Pre({ className, ...props }) {
    const stock = useStockShape();
    return (
      <pre
        className={cn(
          "aui-md-pre border-hair bg-surface-2/30 overflow-x-auto border border-t-0 p-3.5 text-[13px] leading-relaxed",
          stockRadius(stock, "rounded-t-none rounded-b-xl", "rounded-t-none rounded-none"),
          className,
        )}
        {...props}
      />
    );
  },
  code: function Code({ className, ...props }) {
    const isCodeBlock = useIsMarkdownCodeBlock();
    const stock = useStockShape();
    return (
      <code
        className={cn(
          !isCodeBlock &&
            cn(
              "aui-md-inline-code bg-surface-2 px-1.5 py-0.5 font-mono text-[0.85em]",
              stockRadius(stock, "rounded-md"),
            ),
          className,
        )}
        {...props}
      />
    );
  },
  CodeHeader,
});
