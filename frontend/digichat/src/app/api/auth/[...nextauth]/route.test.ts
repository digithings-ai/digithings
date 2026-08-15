import { describe, expect, it, vi } from "vitest";

const { mockGet, mockPost } = vi.hoisted(() => ({
  mockGet: vi.fn(async () => new Response("get")),
  mockPost: vi.fn(async () => new Response("post")),
}));

vi.mock("@/auth", () => ({
  handlers: {
    GET: mockGet,
    POST: mockPost,
  },
}));

import { GET, POST } from "./route";

describe("/api/auth/[...nextauth]", () => {
  it("re-exports NextAuth GET and POST handlers", () => {
    expect(GET).toBe(mockGet);
    expect(POST).toBe(mockPost);
  });
});
