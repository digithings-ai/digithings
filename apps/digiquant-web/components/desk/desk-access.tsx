"use client";

import { usePathname } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { officialApiBase } from "@/lib/official-api";
import {
  findDeskId,
  manifestPath,
  navFromDesk,
  parseManifest,
  selectDesk,
  type Manifest,
  type ManifestDesk,
  type NavGroup,
  type NavNode,
} from "./desk-manifest";
import { isInviteSurface } from "./public-surface";

const DESK_KEY = "dq-desk";

/** Drop invite-only rows. The public rail does not name them. */
function publicNav(groups: NavGroup[]): NavGroup[] {
  const keep = (node: NavNode): NavNode | null => {
    if (isInviteSurface(node.path, node.label)) return null;
    const children = (node.children ?? []).flatMap((child) => {
      const next = keep(child);
      return next ? [next] : [];
    });
    return children.length ? { ...node, children } : { ...node, children: undefined };
  };
  return groups.flatMap((group) => {
    const items = group.items.flatMap((item) => {
      const next = keep(item);
      return next ? [next] : [];
    });
    return items.length ? [{ ...group, items }] : [];
  });
}

type Ctx = {
  manifest: Manifest | null;
  err: string | null;
  desk: ManifestDesk | null;
  setDesk: (id: string) => void;
  nav: NavGroup[];
};

const DeskCtx = createContext<Ctx>({
  manifest: null,
  err: null,
  desk: null,
  setDesk: () => {},
  nav: [],
});

export const useDeskAccess = () => useContext(DeskCtx);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function failReason(status: number, body: unknown): string {
  if (isRecord(body) && isRecord(body.error) && typeof body.error.message === "string") {
    return `/access/manifest failed (${status}): ${body.error.message}`;
  }
  return `/access/manifest failed (${status})`;
}

/**
 * One read of GET /access/manifest. The active desk follows the page when that
 * desk is granted. A seeded manifest skips the fetch (tests).
 */
export function DeskAccess({ children, manifest: seed }: { children: ReactNode; manifest?: Manifest }) {
  const pathname = usePathname() || "/";
  const [loaded, setLoaded] = useState<Manifest | null>(seed ?? null);
  const [err, setErr] = useState<string | null>(null);
  const [deskId, setDeskId] = useState<string | null>(null);
  const manifest = seed ?? loaded;

  useEffect(() => {
    if (seed) return;
    const ac = new AbortController();
    fetch(`${officialApiBase()}/access/manifest`, { signal: ac.signal })
      .then(async (res) => {
        const body: unknown = await res.json().catch(() => null);
        if (!res.ok) throw new Error(failReason(res.status, body));
        const next = parseManifest(body);
        if (!next) throw new Error("/access/manifest returned no desks");
        setLoaded(next);
      })
      .catch((error: unknown) => {
        if (ac.signal.aborted) return;
        setErr(error instanceof Error ? error.message : "failed");
      });
    return () => ac.abort();
  }, [seed]);

  const path = manifestPath(pathname);
  const owner = manifest ? findDeskId(manifest, path, deskId) : null;
  const desk = useMemo(() => selectDesk(manifest, owner ?? deskId), [manifest, owner, deskId]);
  const setDesk = useCallback((id: string) => {
    setDeskId(id);
    try {
      localStorage.setItem(DESK_KEY, id);
    } catch {
      /* storage unavailable */
    }
  }, []);
  const nav = useMemo(() => (desk ? publicNav(navFromDesk(desk)) : []), [desk]);
  const value = useMemo<Ctx>(() => ({ manifest, err, desk, setDesk, nav }), [manifest, err, desk, setDesk, nav]);

  return <DeskCtx.Provider value={value}>{children}</DeskCtx.Provider>;
}
