// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import {
  ArtifactLink,
  ArtifactsPanel,
  artifactBlobPath,
  artifactListPath,
  formatArtifactDate,
  formatArtifactSize,
  isArtifactBlobHref,
  type ArtifactRow,
} from "./artifacts-panel";
import { defaultComponents } from "./markdown-text";

// #2882: the session artifact panel and the artifact link. Three properties
// carry the brief:
//   1. the panel renders rows the server sent;
//   2. view vs download follows the server's `viewable` flag, never a
//      media-type list the client re-derived;
//   3. a dead token answers 410 session_expired and must read as a sentence,
//      not a raw error body.
//
// Every row fixture below is asserted NON-EMPTY before it is used, and each
// split assertion names the row it clicked. A test that could pass because
// the list was empty is the failure mode this file is written against.

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const VIEWABLE: ArtifactRow = {
  id: "a1",
  token: "tok-viewable",
  name: "chart.png",
  mediaType: "image/png",
  byteSize: 2048,
  kind: "image",
  summary: null,
  createdAt: "2026-10-11T09:00:00.000Z",
  viewable: true,
};

const DOWNLOADABLE: ArtifactRow = {
  id: "a2",
  token: "tok-download",
  name: "export.zip",
  mediaType: "application/zip",
  byteSize: 5 * 1024 * 1024,
  kind: "file",
  summary: null,
  createdAt: "2026-10-11T10:00:00.000Z",
  viewable: false,
};

/** Both shapes at once, so no assertion can be satisfied by an empty list. */
const ROWS: ArtifactRow[] = [VIEWABLE, DOWNLOADABLE];
const CONVERSATION = "conv-123";

function listResponse(rows: ArtifactRow[] = ROWS) {
  return {
    ok: true,
    status: 200,
    json: async () => ({ artifacts: rows }),
  } as unknown as Response;
}

describe("artifact helpers", () => {
  it("builds the list path and a blob path that carries the minted token", () => {
    expect(artifactListPath(CONVERSATION)).toBe(
      `/api/conversations/${CONVERSATION}/artifacts`,
    );
    const url = artifactBlobPath(CONVERSATION, VIEWABLE.token);
    expect(url).toBe(
      `/api/conversations/${CONVERSATION}/artifacts/blob?token=${VIEWABLE.token}`,
    );
    // The token is the whole link: strip it and the link cannot resolve.
    expect(new URL(url, "https://x.test").searchParams.get("token")).toBe(
      VIEWABLE.token,
    );
  });

  it("recognises only the artifact blob path", () => {
    expect(isArtifactBlobHref(artifactBlobPath(CONVERSATION, "t"))).toBe(true);
    expect(isArtifactBlobHref("/api/conversations/c/artifacts/blob?token=t#x")).toBe(
      true,
    );
    // Negative controls: the list route, a near miss, an ordinary link.
    expect(isArtifactBlobHref("/api/conversations/c/artifacts")).toBe(false);
    expect(isArtifactBlobHref("/api/conversations/c/artifacts/blobs?token=t")).toBe(
      false,
    );
    expect(isArtifactBlobHref("https://example.test/report.png")).toBe(false);
    expect(isArtifactBlobHref(undefined)).toBe(false);
  });

  it("formats size and date deterministically", () => {
    expect(formatArtifactSize(512)).toBe("512 B");
    expect(formatArtifactSize(2048)).toBe("2 KB");
    expect(formatArtifactSize(5 * 1024 * 1024)).toBe("5 MB");
    expect(formatArtifactSize(-1)).toBe("-");
    expect(formatArtifactDate("2026-10-11T09:00:00.000Z")).toBe("2026-10-11");
    expect(formatArtifactDate("not-a-date")).toBe("-");
  });
});

describe("ArtifactsPanel", () => {
  it("renders a row per artifact from a non-empty list", async () => {
    // Non-vacuity: the fixture must have rows, or this test proves nothing.
    expect(ROWS.length).toBe(2);
    const fetchImpl = vi.fn(async () => listResponse());

    render(
      <ArtifactsPanel
        conversationId={CONVERSATION}
        open
        onClose={() => {}}
        fetchImpl={fetchImpl}
      />,
    );

    expect(await screen.findByText("chart.png")).toBeTruthy();
    expect(screen.getByText("export.zip")).toBeTruthy();
    // Type, size and createdAt are all on the row (DoD 1).
    expect(screen.getByText(/image\/png/)).toBeTruthy();
    expect(screen.getByText(/application\/zip/)).toBeTruthy();
    expect(screen.getByText(/2 KB/)).toBeTruthy();
    expect(screen.getByText(/5 MB/)).toBeTruthy();
    expect(screen.getAllByText(/2026-10-11/)).toHaveLength(2);
    expect(fetchImpl).toHaveBeenCalledWith(
      `/api/conversations/${CONVERSATION}/artifacts`,
    );
  });

  it("opens a viewable row in a new tab and downloads any other row", async () => {
    expect(ROWS.length).toBe(2);
    const openInNewTab = vi.fn((_url: string) => true);
    const navigate = vi.fn((_url: string) => {});
    const user = userEvent.setup();

    render(
      <ArtifactsPanel
        conversationId={CONVERSATION}
        open
        onClose={() => {}}
        fetchImpl={async () => listResponse()}
        openInNewTab={openInNewTab}
        navigate={navigate}
      />,
    );

    const viewable = await screen.findByText("chart.png");
    const downloadable = screen.getByText("export.zip");

    await user.click(viewable);
    expect(openInNewTab).toHaveBeenCalledTimes(1);
    expect(openInNewTab.mock.calls[0][0]).toContain(`token=${VIEWABLE.token}`);
    expect(navigate).not.toHaveBeenCalled();

    await user.click(downloadable);
    expect(navigate).toHaveBeenCalledTimes(1);
    expect(navigate.mock.calls[0][0]).toContain(`token=${DOWNLOADABLE.token}`);
    // The split is the row's flag, not a media-type list: a viewable row
    // never falls through to download, and a non-viewable row never opens a
    // tab. Second click opened nothing further.
    expect(openInNewTab).toHaveBeenCalledTimes(1);
  });

  it("falls back to the same tab when the browser refuses a new tab", async () => {
    expect(ROWS.length).toBe(2);
    const navigate = vi.fn();
    const user = userEvent.setup();

    render(
      <ArtifactsPanel
        conversationId={CONVERSATION}
        open
        onClose={() => {}}
        fetchImpl={async () => listResponse()}
        openInNewTab={() => false}
        navigate={navigate}
      />,
    );

    await user.click(await screen.findByText("chart.png"));
    expect(navigate).toHaveBeenCalledTimes(1);
  });

  it("says so when the session has no artifacts, and when it cannot load them", async () => {
    render(
      <ArtifactsPanel
        conversationId={CONVERSATION}
        open
        onClose={() => {}}
        fetchImpl={async () => listResponse([])}
      />,
    );
    expect(await screen.findByText(/No files in this session yet/)).toBeTruthy();
    cleanup();

    render(
      <ArtifactsPanel
        conversationId={CONVERSATION}
        open
        onClose={() => {}}
        fetchImpl={async () => ({ ok: false, status: 503, json: async () => ({}) }) as unknown as Response}
      />,
    );
    expect(await screen.findByText(/Could not load/)).toBeTruthy();
  });
});

describe("the markdown `a:` override routes artifact links", () => {
  // The wiring test, and the reason it is written as it is. A first attempt
  // asserted only "renders an anchor with this href" and passed against BOTH
  // the routed component and a reverted plain anchor - the two render
  // identical DOM until a link dies. So the discriminator has to be the
  // behaviour that only the artifact route has: a 410 becomes a sentence.
  const Anchor = defaultComponents.a as unknown as React.ComponentType<{
    href?: string;
    children?: React.ReactNode;
  }>;

  it("routes an artifact blob href: a dead token shows the expired state", async () => {
    expect(ROWS.length).toBe(2);
    const dead = {
      ok: false,
      status: 410,
      json: async () => ({ error: "session_expired" }),
    } as unknown as Response;
    const fetchSpy = vi.fn(async () => dead);
    vi.stubGlobal("fetch", fetchSpy);
    const user = userEvent.setup();

    render(<Anchor href={artifactBlobPath(CONVERSATION, VIEWABLE.token)}>chart.png</Anchor>);

    await user.click(screen.getByText("chart.png"));

    // Only the artifact route probes the link and can say this.
    expect(await screen.findByText(/session that has ended/)).toBeTruthy();
    expect(fetchSpy).toHaveBeenCalled();
  });

  it("leaves every other href alone: no probe, no expired state", async () => {
    const fetchSpy = vi.fn(async () => ({ ok: true, status: 200 }) as Response);
    vi.stubGlobal("fetch", fetchSpy);
    const user = userEvent.setup();

    render(<Anchor href="https://example.test/report">report</Anchor>);
    const anchor = screen.getByText("report").closest("a");
    expect(anchor?.getAttribute("href")).toBe("https://example.test/report");

    await user.click(screen.getByText("report"));
    // A plain anchor is not probed and never invents an expired state.
    expect(screen.queryByText(/session that has ended/)).toBeNull();
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe("ArtifactLink", () => {
  const HREF = artifactBlobPath(CONVERSATION, VIEWABLE.token);

  it("carries the minted token and opens the link when it is live", async () => {
    const openInNewTab = vi.fn((_url: string) => true);
    const navigate = vi.fn((_url: string) => {});
    const user = userEvent.setup();

    render(
      <ArtifactLink
        href={HREF}
        fetchImpl={async () => ({ ok: true, status: 200 }) as Response}
        openInNewTab={openInNewTab}
        navigate={navigate}
      >
        chart.png
      </ArtifactLink>,
    );

    const anchor = screen.getByText("chart.png").closest("a");
    expect(anchor?.getAttribute("href")).toBe(HREF);
    expect(anchor?.getAttribute("href")).toContain(`token=${VIEWABLE.token}`);

    await user.click(screen.getByText("chart.png"));
    expect(openInNewTab).toHaveBeenCalledWith(HREF);
    expect(navigate).not.toHaveBeenCalled();
  });

  it("shows the session-expired state for a dead token instead of a raw error", async () => {
    // The blob route's exact answer for a token the session no longer owns.
    const expired = {
      ok: false,
      status: 410,
      json: async () => ({ error: "session_expired" }),
    } as unknown as Response;
    const openInNewTab = vi.fn((_url: string) => true);
    const navigate = vi.fn((_url: string) => {});
    const user = userEvent.setup();

    render(
      <ArtifactLink
        href={HREF}
        fetchImpl={async () => expired}
        openInNewTab={openInNewTab}
        navigate={navigate}
      >
        chart.png
      </ArtifactLink>,
    );

    await user.click(screen.getByText("chart.png"));

    expect(await screen.findByText(/session that has ended/)).toBeTruthy();
    // The dead link must not be followed into a raw JSON error.
    expect(openInNewTab).not.toHaveBeenCalled();
    expect(navigate).not.toHaveBeenCalled();
    // The error code is never rendered verbatim.
    expect(screen.queryByText(/"session_expired"/)).toBeNull();
  });

  it("follows the link when the probe cannot be completed", async () => {
    const openInNewTab = vi.fn(() => true);
    const user = userEvent.setup();

    render(
      <ArtifactLink
        href={HREF}
        fetchImpl={async () => {
          throw new Error("offline");
        }}
        openInNewTab={openInNewTab}
      >
        chart.png
      </ArtifactLink>,
    );

    await user.click(screen.getByText("chart.png"));
    expect(openInNewTab).toHaveBeenCalledWith(HREF);
  });
});