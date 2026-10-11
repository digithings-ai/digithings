import { nestToc, type TocEntry } from "@/lib/book/toc";

/**
 * A chapter's heading rail (DIG-2821).
 *
 * Rendered as a `<nav>` with an ordered list, because a table of contents is a
 * list of links with no other job. Indentation comes from the heading's level
 * so a level jump in the source does not break the outline.
 */
export default function ChapterRail({ entries, label = "On this page" }: { entries: readonly TocEntry[]; label?: string }) {
  const tree = nestToc(entries);
  if (tree.length === 0) return null;
  return (
    <nav aria-label={label} className="font-mono text-[0.8rem]">
      <p className="m-0 text-accent">{label}</p>
      <Branch nodes={tree} />
    </nav>
  );
}

function Branch({ nodes }: { nodes: ReturnType<typeof nestToc> }) {
  return (
    <ol className="m-0 list-none p-0">
      {nodes.map((node) => (
        <li key={node.id} style={{ paddingLeft: `${(node.level - 2) * 0.75}rem` }} className="py-1">
          <a href={`#${node.id}`} className="text-ink-soft">
            {node.text}
          </a>
          {node.children.length > 0 ? <Branch nodes={node.children} /> : null}
        </li>
      ))}
    </ol>
  );
}
