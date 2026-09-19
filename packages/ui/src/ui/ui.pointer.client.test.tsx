// @vitest-environment happy-dom
/**
 * Menu/select item pointer cursors (#4306, phase 0.3).
 *
 * `DropdownMenuContent` is portal-only, so react-dom/server never sees its
 * items — this is the DOM half of the kit-level cursor contract. Every
 * activatable row is `cursor-pointer`; disabled rows name `not-allowed`
 * instead of falling back to the stock `cursor-default`.
 */
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "./index";

beforeAll(() => {
  (
    globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

afterEach(() => {
  document.body.replaceChildren();
});

async function mount(ui: React.ReactElement) {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(ui);
  });
  return async () => {
    await act(async () => root.unmount());
    host.remove();
  };
}

describe("kit menu items carry the pointer cursor", () => {
  it("items and checkbox/radio rows are pointer; disabled rows are not-allowed", async () => {
    const unmount = await mount(
      <DropdownMenu defaultOpen>
        <DropdownMenuTrigger>Menu</DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem>One</DropdownMenuItem>
          <DropdownMenuItem disabled>Two</DropdownMenuItem>
          <DropdownMenuCheckboxItem checked>Three</DropdownMenuCheckboxItem>
          <DropdownMenuRadioGroup value="four">
            <DropdownMenuRadioItem value="four">Four</DropdownMenuRadioItem>
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>,
    );

    const items = document.querySelectorAll('[data-slot="dropdown-menu-item"]');
    expect(items.length).toBe(2);
    expect(items[0]?.className).toContain("cursor-pointer");
    expect(items[1]?.className).toContain("cursor-pointer");
    expect(items[1]?.className).toContain("data-disabled:cursor-not-allowed");

    const checkbox = document.querySelector(
      '[data-slot="dropdown-menu-checkbox-item"]',
    );
    const radio = document.querySelector(
      '[data-slot="dropdown-menu-radio-item"]',
    );
    expect(checkbox?.className).toContain("cursor-pointer");
    expect(checkbox?.className).toContain("data-disabled:cursor-not-allowed");
    expect(radio?.className).toContain("cursor-pointer");
    expect(radio?.className).toContain("data-disabled:cursor-not-allowed");

    await unmount();
  });

  it("sub-triggers are pointer too", async () => {
    const unmount = await mount(
      <DropdownMenu defaultOpen>
        <DropdownMenuTrigger>Menu</DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuSub>
            <DropdownMenuSubTrigger>More</DropdownMenuSubTrigger>
            <DropdownMenuSubContent>
              <DropdownMenuItem>Nested</DropdownMenuItem>
            </DropdownMenuSubContent>
          </DropdownMenuSub>
        </DropdownMenuContent>
      </DropdownMenu>,
    );

    const trigger = document.querySelector(
      '[data-slot="dropdown-menu-sub-trigger"]',
    );
    expect(trigger?.className).toContain("cursor-pointer");
    await unmount();
  });
});
