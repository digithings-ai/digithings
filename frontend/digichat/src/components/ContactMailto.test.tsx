// @vitest-environment happy-dom
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ContactMailto } from "@/components/ContactMailto";

describe("ContactMailto", () => {
  it("assigns the real mailto: href and swaps in the address text after mount", () => {
    render(<ContactMailto email="ops@example.com" />);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "mailto:ops@example.com");
    expect(link).toHaveTextContent("ops@example.com");
  });

  it("passes through className and style", () => {
    render(
      <ContactMailto
        email="ops@example.com"
        className="font-medium underline"
        style={{ color: "red" }}
      />,
    );
    const link = screen.getByRole("link");
    expect(link).toHaveClass("font-medium", "underline");
    expect(link).toHaveStyle({ color: "red" });
  });

  it("re-runs the mount effect when email changes, updating href and text", () => {
    const { rerender } = render(<ContactMailto email="a@example.com" />);
    expect(screen.getByRole("link")).toHaveAttribute("href", "mailto:a@example.com");

    rerender(<ContactMailto email="b@example.com" />);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "mailto:b@example.com");
    expect(link).toHaveTextContent("b@example.com");
  });
});
