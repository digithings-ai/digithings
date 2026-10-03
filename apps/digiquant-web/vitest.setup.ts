import { vi } from "vitest";

// next/font/google is an empty module that the Next compiler replaces.
// Vitest has no compiler, so hand back a class the chat frame can attach.
vi.mock("next/font/google", () => {
  const load = (name: string) => () => ({
    variable: name,
    className: name,
    style: { fontFamily: name },
  });
  return {
    Geist_Mono: load("Geist_Mono"),
    Inter: load("Inter"),
    JetBrains_Mono: load("JetBrains_Mono"),
  };
});

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/app/brief/",
}));
