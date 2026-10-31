// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from "vitest";
import { findThreadComposer } from "./skin-palette-bridge";

afterEach(() => {
  document.body.replaceChildren();
});

function html(markup: string): HTMLElement {
  const scope = document.createElement("div");
  scope.innerHTML = markup;
  document.body.append(scope);
  return scope;
}

describe("findThreadComposer", () => {
  it("picks the thread composer, not an edit composer inside a message", () => {
    const scope = html(`
      <div data-message-id="m1"><form id="edit"><textarea></textarea></form></div>
      <form id="thread"><textarea></textarea></form>
    `);
    expect(findThreadComposer(scope)?.id).toBe("thread");
  });

  it("accepts a rich-text (contenteditable) composer", () => {
    const scope = html(`<form id="rich"><div contenteditable="true"></div></form>`);
    expect(findThreadComposer(scope)?.id).toBe("rich");
  });

  it("ignores forms without a text input", () => {
    const scope = html(`<form id="search"><input type="checkbox" /></form>`);
    expect(findThreadComposer(scope)).toBeNull();
  });

  it("prefers the composer being typed in when the skin renders two", () => {
    const scope = html(`
      <form id="mobile"><textarea id="mobile-input"></textarea></form>
      <form id="desktop"><textarea></textarea></form>
    `);
    (scope.querySelector("#mobile-input") as HTMLTextAreaElement).focus();
    expect(findThreadComposer(scope)?.id).toBe("mobile");
  });

  it("prefers a focused popover composer over a hidden one in the scope", () => {
    const scope = html(`<form id="hidden-desktop"><textarea></textarea></form>`);
    html(`<div data-radix-popper-content-wrapper><form id="modal"><textarea id="modal-input"></textarea></form></div>`);
    (document.querySelector("#modal-input") as HTMLTextAreaElement).focus();
    expect(findThreadComposer(scope)?.id).toBe("modal");
  });

  it("falls back to a composer the skin opened in a popover portal", () => {
    const scope = html(`<button>open</button>`);
    html(`<div data-radix-popper-content-wrapper><form id="modal"><textarea></textarea></form></div>`);
    html(`<form id="unrelated"><textarea></textarea></form>`);
    expect(findThreadComposer(scope)?.id).toBe("modal");
  });
});
