'use client';

import { useState, type ReactNode } from 'react';
import Link from 'next/link';
import { Button } from '@digithings/ui/ui';
import { DeskPicker } from '@/components/desk/shell/DeskPicker';
import type { DeskId, RailNode } from '@/lib/desk/spine';

function RailBranch({
  node,
  activeId,
  collapsed,
  depth,
}: {
  node: RailNode;
  activeId: string;
  collapsed: boolean;
  depth: number;
}) {
  const hasChildren = (node.children?.length ?? 0) > 0;
  const [open, setOpen] = useState(true);
  const expanded = hasChildren && open;
  const current = node.id === activeId;

  return (
    <div data-rail-node={node.id}>
      <div className="flex items-center" style={{ paddingLeft: collapsed ? 0 : depth * 12 }}>
        <Link
          href={node.href}
          aria-current={current ? 'page' : undefined}
          className={`flex min-w-0 flex-1 items-center gap-2 px-3 py-1.5 font-mono text-[0.78rem] ${
            current ? 'bg-ink/[0.04] text-ink' : 'text-ink-soft hover:bg-ink/[0.03] hover:text-ink'
          }`}
        >
          <span className={collapsed ? 'sr-only' : 'truncate'}>{node.label}</span>
          {node.badge && !collapsed ? (
            <span className="text-ink-mute">[{node.badge}]</span>
          ) : null}
        </Link>
        {hasChildren && !collapsed ? (
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            aria-expanded={expanded}
            aria-label={`${expanded ? 'Collapse' : 'Expand'} ${node.label}`}
            onClick={() => setOpen((value) => !value)}
          >
            {expanded ? '–' : '+'}
          </Button>
        ) : null}
      </div>
      {hasChildren && expanded && !collapsed ? (
        <div>
          {node.children?.map((child) => (
            <RailBranch
              key={child.id}
              node={child}
              activeId={activeId}
              collapsed={collapsed}
              depth={depth + 1}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function DeskRail({
  nodes,
  activeId,
  collapsed,
  deskId,
  fxHubOnly,
  footer,
}: {
  nodes: readonly RailNode[];
  activeId: string;
  collapsed: boolean;
  deskId: DeskId;
  fxHubOnly: boolean;
  footer?: ReactNode;
}) {
  return (
    <aside
      id="app-sidebar-nav"
      aria-label="Sidebar"
      data-desk-rail=""
      className="flex min-h-0 flex-col border-r border-hair bg-surface"
    >
      <div className={collapsed ? 'sr-only' : 'border-b border-hair p-2'}>
        <DeskPicker deskId={deskId} fxHubOnly={fxHubOnly} />
      </div>
      <nav aria-label="Primary" className="min-h-0 flex-1 overflow-y-auto py-2">
        {nodes.map((node) => (
          <RailBranch
            key={node.id}
            node={node}
            activeId={activeId}
            collapsed={collapsed}
            depth={0}
          />
        ))}
      </nav>
      {footer ? <div className="shrink-0 border-t border-hair p-2">{footer}</div> : null}
    </aside>
  );
}
