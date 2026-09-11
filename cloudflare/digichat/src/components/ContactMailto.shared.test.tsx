// @vitest-environment happy-dom
// Behavioral tests for the shared @digithings/web ContactMailto as consumed
// by the embed paywall card (implementation contracts live beside the
// component in the web workspace).
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ContactMailto } from "@digithings/web";

describe("ContactMailto", () => {
  it("assigns the real mailto: href and swaps in the address text after mount", () => {
    render(<ContactMailto email="ops@example.com" showAddress />);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "mailto:ops@example.com");
    expect(link).toHaveTextContent("ops@example.com");
  });

  it("passes through className and style", () => {
    render(
      <ContactMailto
        email="ops@example.com"
        showAddress
        className="font-medium underline"
        style={{ color: "red" }}
      />,
    );
    const link = screen.getByRole("link");
    expect(link).toHaveClass("font-medium", "underline");
    expect(link).toHaveStyle({ color: "red" });
  });

  it("re-runs the mount effect when email changes, updating href and text", () => {
    const { rerender } = render(<ContactMailto email="a@example.com" showAddress />);
    expect(screen.getByRole("link")).toHaveAttribute("href", "mailto:a@example.com");

    rerender(<ContactMailto email="b@example.com" showAddress />);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "mailto:b@example.com");
    expect(link).toHaveTextContent("b@example.com");
  });
});
