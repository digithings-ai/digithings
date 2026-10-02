"use client";

import Link from "next/link";
import { useState, type KeyboardEvent } from "react";
import { Button } from "@digithings/ui/ui";
import { useDeskAccess } from "./desk-access";
import { canOpenDeskPath, sectionOf, type NavNode } from "./desk-manifest";
import { deskHref } from "./paths";

function Tag({ node }: { node: NavNode }) {
  if (node.lock) return <span className="nav-tag">[{node.lock}]</span>;
  return node.status ? <span className="nav-tag">[{node.status}]</span> : null;
}

function PathLink({
  node,
  current,
  folder,
  parent,
}: {
  node: NavNode;
  current: string;
  folder?: boolean;
  parent?: string;
}) {
  const here = current === node.path;
  const className = `nav-link${here ? " on" : ""}${node.lock ? " locked" : ""}`;
  const body = (
    <>
      <span className="nav-path">{node.path}</span>
      <Tag node={node} />
    </>
  );
  if (!canOpenDeskPath(node.path)) {
    return (
      <span className={className} data-path={node.path} title={node.path}>
        {body}
      </span>
    );
  }
  return (
    <Link
      href={deskHref(node.path)}
      data-path={node.path}
      data-folder={folder ? "1" : undefined}
      data-parent={parent}
      className={className}
      aria-current={here ? "page" : undefined}
      title={node.path}
    >
      {body}
    </Link>
  );
}

/**
 * Sidebar as a folder listing: every line is a slash path behind a triangle.
 * ▾ open, ▸ closed or leaf. Folders toggle with the triangle; the path navigates.
 */
export function DeskRail({ current }: { current: string }) {
  const { nav, manifest, err } = useDeskAccess();
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const active = sectionOf(current);
  const isOpen = (path: string) => open[path] ?? path === active;

  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.altKey || event.metaKey || event.ctrlKey) return;
    const links = [...event.currentTarget.querySelectorAll<HTMLAnchorElement>("a.nav-link")];
    const index = links.indexOf(document.activeElement as HTMLAnchorElement);
    if (index < 0) return;
    const cur = links[index];
    const folder = cur.dataset.folder === "1";
    const path = cur.dataset.path ?? "";
    let to: HTMLAnchorElement | undefined;
    if (event.key === "ArrowDown") to = links[Math.min(index + 1, links.length - 1)];
    else if (event.key === "ArrowUp") to = links[Math.max(index - 1, 0)];
    else if (event.key === "Home") to = links[0];
    else if (event.key === "End") to = links[links.length - 1];
    else if (event.key === "ArrowRight" && folder) {
      if (!isOpen(path)) setOpen((state) => ({ ...state, [path]: true }));
      else to = links[index + 1];
    } else if (event.key === "ArrowLeft") {
      if (folder && isOpen(path)) setOpen((state) => ({ ...state, [path]: false }));
      else if (cur.dataset.parent) to = links.find((link) => link.dataset.path === cur.dataset.parent);
    } else return;
    event.preventDefault();
    to?.focus();
  };

  return (
    <aside className="rail">
      <div className="rail-head">
        <span>~/pages</span>
      </div>
      <nav className="nav-tree" aria-label="Pages" onKeyDown={onKeyDown}>
        {!nav.length ? (
          <p className="nav-empty">{err ? "access unavailable" : manifest ? "no pages" : "loading…"}</p>
        ) : null}
        {nav.map((group, index) => (
          <div className="nav-group" key={`${group.title ?? "pages"}-${index}`}>
            {group.title ? <div className="nav-title">{group.title}</div> : null}
            {group.items.map((node) => {
              const kids = node.children ?? [];
              return (
                <div key={node.path}>
                  <div className="nav-row">
                    {kids.length ? (
                      <Button
                        type="button"
                        variant="ghost"
                        className="nav-tri"
                        aria-expanded={isOpen(node.path)}
                        aria-label={`${isOpen(node.path) ? "Collapse" : "Expand"} ${node.path}`}
                        onClick={() => setOpen((state) => ({ ...state, [node.path]: !isOpen(node.path) }))}
                      >
                        {isOpen(node.path) ? "▾" : "▸"}
                      </Button>
                    ) : (
                      <span className="nav-tri leaf" aria-hidden="true">
                        ▸
                      </span>
                    )}
                    <PathLink node={node} current={current} folder={kids.length > 0} />
                  </div>
                  {kids.length && isOpen(node.path)
                    ? kids.map((child) => (
                        <div className="nav-row kid" key={child.path}>
                          <span className="nav-tri leaf" aria-hidden="true">
                            ▸
                          </span>
                          <PathLink node={child} current={current} parent={node.path} />
                        </div>
                      ))
                    : null}
                </div>
              );
            })}
          </div>
        ))}
      </nav>
    </aside>
  );
}
