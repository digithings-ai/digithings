// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SAVE_PROMPT_SLOT, SAVE_URL_LIFETIME_MS, saveTextFile } from "./save-file";

type Nav = Navigator & {
  share?: unknown;
  canShare?: unknown;
  userActivation?: unknown;
};

const clicks: Array<{ download: string; href: string }> = [];
let revoked: string[] = [];

function setPointer(coarse: boolean) {
  window.matchMedia = ((q: string) => ({
    matches: coarse && q.includes("coarse"),
    media: q,
    addEventListener() {},
    removeEventListener() {},
  })) as unknown as typeof window.matchMedia;
}

function setActivation(active: boolean | null) {
  Object.defineProperty(navigator, "userActivation", {
    configurable: true,
    value: active === null ? undefined : { isActive: active },
  });
}

function setShare(share: ((d: ShareData) => Promise<void>) | undefined) {
  const nav = navigator as Nav;
  Object.defineProperty(nav, "share", { configurable: true, value: share });
  Object.defineProperty(nav, "canShare", {
    configurable: true,
    value: share ? (d: ShareData) => Boolean(d.files?.length) : undefined,
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  clicks.length = 0;
  revoked = [];
  let n = 0;
  URL.createObjectURL = vi.fn(() => `blob:test/${++n}`);
  URL.revokeObjectURL = vi.fn((u: string) => void revoked.push(u));
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    clicks.push({ download: this.download, href: this.href });
  });
  setPointer(false);
  setActivation(true);
  setShare(undefined);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

describe("saveTextFile", () => {
  it("downloads on desktop and keeps the blob URL alive for iOS's confirm step", () => {
    saveTextFile("digichat.md", "# hi", "text/markdown;charset=utf-8");
    expect(clicks).toEqual([{ download: "digichat.md", href: "blob:test/1" }]);
    vi.advanceTimersByTime(2_000);
    expect(revoked).toEqual([]);
    vi.advanceTimersByTime(SAVE_URL_LIFETIME_MS);
    expect(revoked).toEqual(["blob:test/1"]);
  });

  it("uses the share sheet on a phone with the right name and type", async () => {
    setPointer(true);
    const share = vi.fn(async () => {});
    setShare(share);
    saveTextFile("chat.html", "<p>x</p>", "text/html;charset=utf-8");
    expect(share).toHaveBeenCalledTimes(1);
    const file = (share.mock.calls[0] as unknown as [ShareData])[0].files![0]!;
    expect(file.name).toBe("chat.html");
    expect(file.type).toBe("text/html;charset=utf-8");
    await vi.runAllTimersAsync();
    expect(clicks).toEqual([]);
  });

  it("does nothing more when the visitor closes the share sheet", async () => {
    setPointer(true);
    setShare(async () => {
      throw Object.assign(new Error("closed"), { name: "AbortError" });
    });
    saveTextFile("digichat.md", "x", "text/markdown");
    await vi.runAllTimersAsync();
    expect(clicks).toEqual([]);
  });

  it("falls back to a download when sharing is refused", async () => {
    setPointer(true);
    setShare(async () => {
      throw Object.assign(new Error("nope"), { name: "NotAllowedError" });
    });
    saveTextFile("digichat.md", "x", "text/markdown");
    await vi.advanceTimersByTimeAsync(0);
    expect(clicks.map((c) => c.download)).toEqual(["digichat.md"]);
  });

  it("downloads in a frame that is not allowed to share", () => {
    setPointer(true);
    const share = vi.fn(async () => {});
    setShare(share);
    Object.defineProperty(document, "featurePolicy", {
      configurable: true,
      value: { allowsFeature: (f: string) => f !== "web-share" },
    });
    try {
      saveTextFile("digichat.md", "x", "text/markdown");
    } finally {
      Object.defineProperty(document, "featurePolicy", { configurable: true, value: undefined });
    }
    expect(share).not.toHaveBeenCalled();
    expect(clicks.map((c) => c.download)).toEqual(["digichat.md"]);
  });

  it("asks for one more tap when the activation expired, then saves", () => {
    setActivation(false);
    saveTextFile("chat.html", "<p>x</p>", "text/html");
    expect(clicks).toEqual([]);
    const prompt = document.querySelector(`[data-slot='${SAVE_PROMPT_SLOT}']`);
    expect(prompt?.textContent).toContain("chat.html is ready");
    setActivation(true);
    (document.querySelector(`[data-slot='${SAVE_PROMPT_SLOT}-save']`) as HTMLButtonElement).click();
    expect(clicks.map((c) => c.download)).toEqual(["chat.html"]);
    expect(document.querySelector(`[data-slot='${SAVE_PROMPT_SLOT}']`)).toBeNull();
  });

  it("keeps one prompt at a time and can be dismissed", () => {
    setActivation(false);
    saveTextFile("a.html", "a", "text/html");
    saveTextFile("b.html", "b", "text/html");
    const prompts = document.querySelectorAll(`[data-slot='${SAVE_PROMPT_SLOT}']`);
    expect(prompts.length).toBe(1);
    expect(prompts[0]?.textContent).toContain("b.html");
    (document.querySelector("[aria-label='Dismiss']") as HTMLButtonElement).click();
    expect(document.querySelector(`[data-slot='${SAVE_PROMPT_SLOT}']`)).toBeNull();
    expect(clicks).toEqual([]);
  });
});
