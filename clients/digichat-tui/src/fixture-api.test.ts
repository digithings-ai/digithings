import { expect, test } from "bun:test";

import { startFixtureApi } from "./fixture-api";

test("the fixture API serves the conversation list and one conversation", async () => {
  const api = await startFixtureApi();
  try {
    const list = await fetch(`${api.url}/api/conversations`);
    expect(list.status).toBe(200);
    const body = (await list.json()) as { conversations: { id: string }[] };
    expect(body.conversations[0]?.id).toBe("s1");

    const conversation = await fetch(`${api.url}/api/conversations/s1`);
    expect(conversation.status).toBe(200);
    const messages = (await conversation.json()) as { messages: { role: string }[] };
    expect(messages.messages.length).toBeGreaterThan(0);

    // The fixture counts what it served: the exporter refuses a frame the
    // client did not read here.
    expect(api.served()).toBe(2);
  } finally {
    await api.close();
  }
});

test("the fixture API refuses every other route", async () => {
  const api = await startFixtureApi();
  try {
    const other = await fetch(`${api.url}/api/v1/chat`);
    expect(other.status).toBe(404);
    const body = (await other.json()) as { error: { code: string } };
    expect(body.error.code).toBe("not_found");
  } finally {
    await api.close();
  }
});

test("the fixture API listens on loopback only", async () => {
  const api = await startFixtureApi();
  try {
    expect(api.url.startsWith("http://127.0.0.1:")).toBe(true);
  } finally {
    await api.close();
  }
});