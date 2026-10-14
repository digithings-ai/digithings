/** Gloomberb tools surface. Names come from the MCP registry (`gloomberb_*`). */
export function GloomberbTools({ tools = [] }: { tools?: readonly string[] }) {
  return (
    <section aria-label="Gloomberb" className="m-px flex min-h-0 flex-1 flex-col bg-surface">
      <h1 className="m-0 flex h-7 shrink-0 items-center border-b border-hair px-2.5 font-mono text-[0.6875rem] font-normal tracking-[0.04em] text-ink-mute">
        Gloomberb
      </h1>
      {tools.length === 0 ? (
        <p className="m-0 px-2.5 py-2 font-mono text-[0.75rem] leading-[1.45] text-ink-mute">
          Gloomberb tools are not mounted on this desk yet.
        </p>
      ) : (
        <ul className="m-0 list-none px-2.5 py-2 font-mono text-[0.75rem] leading-[1.45] text-ink">
          {tools.map((tool) => (
            <li key={tool}>{tool}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
