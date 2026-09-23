"use client";
/**
 * Architecture diagram — a system drawn the way engineers draw it: named boxes
 * for services, a boundary around what you own, and labelled connectors between
 * them.
 *
 * WHAT IT IS. Mermaid's `architecture-beta` grammar (added in mermaid 11.1,
 * refined in 11.16 with `align`), rendered through the exact pipeline the chat
 * surface already uses — `theme: "base"` with every `themeVariable` filled from
 * the computed design tokens, lazily imported, sanitized by mermaid's own
 * strict mode, source-preserving as the no-JS fallback. See
 * `ChatMermaidBlock.tsx` for the four canon rules; this component inherits all
 * of them and adds nothing to the package that was not already there.
 *
 * WHY MERMAID RATHER THAN A NEW DEPENDENCY. `mermaid` is already a `packages/ui`
 * dependency (the chat fence draws with it), so an architecture diagram costs
 * the bundle nothing new and inherits the token theming for free. The house
 * alternative, `beautiful-mermaid`, is pure and build-time safe but supports
 * only flowchart/state/sequence/class/ER/charts — it has no architecture
 * grammar. If the force-directed layout ever becomes the blocker, the escape
 * hatch is `@xyflow/react` + `elkjs` with a kit-owned grammar; this component's
 * prop surface is deliberately the declarative spec, so only the renderer would
 * change.
 *
 * THE SPEC IS THE API, NOT THE MERMAID SOURCE. Callers pass a small typed spec
 * and `toMermaid()` emits the diagram source. That keeps mermaid's syntax in one
 * place, makes the diagram unit-testable without a DOM (see
 * `architecture.test.ts`), and means the same spec can later be handed to an
 * export path, a docs page, or a model prompt.
 *
 * KNOWN LIMITATION, DOCUMENTED SO NOBODY REDISCOVERS IT. architecture-beta is
 * still beta and its layout is force-directed: a service can carry only ONE
 * edge per side, so two connectors leaving the same side of the same box are
 * not representable — the last one wins. Use the `fromSide`/`toSide` fields to
 * spread a fan-out across sides, or introduce a `junction` (spec `junctions`)
 * when a genuine four-way split is needed. There is no manual positioning and
 * edges cannot carry labels.
 */

import { useEffect, useId, useRef, useState } from "react";

import { tokenThemeVariables } from "./mermaid-theme";

/** The five icons mermaid's architecture grammar ships with. */
export type ArchIcon = "cloud" | "database" | "disk" | "internet" | "server";

/** Which side of a box a connector attaches to. */
export type ArchSide = "T" | "R" | "B" | "L";

/** A titled boundary. Nesting is expressed with `parent`. */
export interface ArchGroup {
  id: string;
  label: string;
  icon?: ArchIcon;
  /** Id of the group this one sits inside. */
  parent?: string;
}

/** One service box. `group` places it inside a boundary. */
export interface ArchService {
  id: string;
  label: string;
  icon?: ArchIcon;
  group?: string;
}

/** One connector. Sides are explicit because mermaid cannot fan out a side. */
export interface ArchEdge {
  from: string;
  to: string;
  /** Defaults to "R". */
  fromSide?: ArchSide;
  /** Defaults to "L". */
  toSide?: ArchSide;
  /** Arrow only at `to` (the default), only at `from`, or neither. */
  arrow?: "to" | "from" | "none";
  /**
   * What travels along the connector ("https", "sql", "traces"). Plain words and
   * spaces only — mermaid's edge-title token is the same restricted one the box
   * titles use, so punctuation is not representable here.
   */
  label?: string;
}

/** A four-way split point. Rarely needed; see the module docblock. */
export interface ArchJunction {
  id: string;
  group?: string;
}

/** `align row a b c` / `align column a b c`, for taming the force layout. */
export interface ArchAlign {
  axis: "row" | "column";
  ids: string[];
}

export interface ArchSpec {
  /** Short accessible title. */
  title: string;
  /** One sentence describing the shape, for screen readers. */
  description: string;
  groups?: ArchGroup[];
  services: ArchService[];
  junctions?: ArchJunction[];
  edges: ArchEdge[];
  aligns?: ArchAlign[];
}

/**
 * A box title. mermaid's `ARCH_TITLE` token accepts one of three shapes — a
 * double-quoted string, a single-quoted string, or `[\w ]+` unquoted — so any
 * punctuation (a `·`, a colon, an em dash) forces the quoted form. Escaping
 * `\` and `"` is the caller's text surviving the grammar's own escape rule.
 */
function archTitle(text: string): string {
  if (/^[\w ]*$/.test(text)) return `[${text}]`;
  return `["${text.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"]`;
}

function groupDeclaration(group: ArchGroup): string {
  const icon = group.icon ? `(${group.icon})` : "";
  const parent = group.parent ? ` in ${group.parent}` : "";
  return `group ${group.id}${icon}${archTitle(group.label)}${parent}`;
}

function serviceDeclaration(service: ArchService): string {
  const icon = service.icon ? `(${service.icon})` : "";
  const group = service.group ? ` in ${service.group}` : "";
  return `service ${service.id}${icon}${archTitle(service.label)}${group}`;
}

/**
 * One connector. mermaid's arrow grammar is `lhs:SIDE [<] (-- | -[label]-) [>] SIDE:rhs`,
 * so an arrow and a label coexist as `-[label]->` and a bare edge is `--`.
 */
function edgeDeclaration(edge: ArchEdge): string {
  const fromSide = edge.fromSide ?? "R";
  const toSide = edge.toSide ?? "L";
  const arrow = edge.arrow ?? "to";
  const dash = edge.label ? `-[${edge.label}]-` : "--";
  const left = arrow === "from" ? "<" : "";
  const right = arrow === "to" ? ">" : "";
  return `${edge.from}:${fromSide} ${left}${dash}${right} ${toSide}:${edge.to}`;
}

/**
 * Parents before children, so a nested `group ... in parent` is never emitted
 * before the group it names. Stable for a flat list.
 */
function groupsInOrder(groups: readonly ArchGroup[]): ArchGroup[] {
  const byId = new Map(groups.map((group) => [group.id, group]));
  const seen = new Set<string>();
  const out: ArchGroup[] = [];
  const visit = (group: ArchGroup, guard: Set<string>): void => {
    if (seen.has(group.id) || guard.has(group.id)) return;
    guard.add(group.id);
    if (group.parent) {
      const parent = byId.get(group.parent);
      if (parent) visit(parent, guard);
    }
    seen.add(group.id);
    out.push(group);
  };
  for (const group of groups) visit(group, new Set());
  return out;
}

/**
 * Render the spec as `architecture-beta` source. Pure — no DOM, no async — so
 * a unit test can assert the exact diagram a caller will draw.
 */
export function toMermaid(spec: ArchSpec): string {
  const lines: string[] = ["architecture-beta"];
  lines.push(`    accTitle: ${spec.title}`);
  lines.push(`    accDescr: ${spec.description}`);

  const groups = groupsInOrder(spec.groups ?? []);
  if (groups.length > 0) {
    lines.push("");
    for (const group of groups) lines.push(`    ${groupDeclaration(group)}`);
  }

  lines.push("");
  for (const service of spec.services) lines.push(`    ${serviceDeclaration(service)}`);

  const junctions = spec.junctions ?? [];
  if (junctions.length > 0) {
    lines.push("");
    for (const junction of junctions) {
      lines.push(`    junction ${junction.id}${junction.group ? ` in ${junction.group}` : ""}`);
    }
  }

  if (spec.edges.length > 0) {
    lines.push("");
    for (const edge of spec.edges) lines.push(`    ${edgeDeclaration(edge)}`);
  }

  const aligns = spec.aligns ?? [];
  if (aligns.length > 0) {
    lines.push("");
    for (const align of aligns) {
      lines.push(`    align ${align.axis} ${align.ids.join(" ")}`);
    }
  }

  return lines.join("\n");
}

export type ArchitectureDiagramProps = {
  spec: ArchSpec;
  /** Mono caption under the figure. Defaults to the spec title. */
  caption?: string;
  className?: string;
};

export function ArchitectureDiagram({ spec, caption, className }: ArchitectureDiagramProps) {
  const [svg, setSvg] = useState("");
  const [failed, setFailed] = useState(false);
  const [themeTick, setThemeTick] = useState(0);
  const hostRef = useRef<HTMLElement>(null);
  const id = `arch-${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  const source = toMermaid(spec);

  useEffect(() => {
    const observer = new MutationObserver(() => setThemeTick((n) => n + 1));
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let cancelled = false;

    void (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          suppressErrorRendering: true,
          theme: "base",
          themeVariables: tokenThemeVariables(host),
          flowchart: { htmlLabels: false, useMaxWidth: true },
          sequence: { useMaxWidth: true },
        });
        // Validate first: parse throws on a malformed graph without touching
        // the document, so the failure path never leaves stray nodes behind.
        await mermaid.parse(source);
        const rendered = await mermaid.render(id, source);
        if (cancelled) return;
        setSvg(rendered.svg);
        setFailed(false);
      } catch {
        if (cancelled) return;
        setSvg("");
        setFailed(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [source, id, themeTick]);

  const drawn = Boolean(svg) && !failed;
  const cls = ["arch-figure", className ?? ""].filter(Boolean).join(" ");

  return (
    <figure
      ref={hostRef}
      className={cls}
      data-state={failed ? "source" : drawn ? "diagram" : "pending"}
    >
      <div
        className="arch-figure__body"
        role="img"
        aria-label={`${spec.title}. ${spec.description}`}
        // mermaid.render returns a sanitized SVG string under
        // securityLevel: "strict" — see ChatMermaidBlock's docblock.
        dangerouslySetInnerHTML={drawn ? { __html: svg } : undefined}
      />
      {!drawn ? (
        <pre className="arch-figure__source">
          <code>{source}</code>
        </pre>
      ) : null}
      <figcaption className="arch-figure__caption">{caption ?? spec.title}</figcaption>
    </figure>
  );
}
