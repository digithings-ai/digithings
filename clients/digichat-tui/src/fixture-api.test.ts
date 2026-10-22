import { expect, test } from "bun:test";

import { startFixtureApi } from "./fixture-api";

test("the fixture API serves the conversation list and one conversation", async () => {
  const api = startFixtureApi();
  try {
    const list = await fetch(`${api.url}/api/conversations`);
    expect(list.status).toBe(200);
    const body = (await list.json()) as { conversations: { id: string }[] };
    expect(body.conversations[0]?.id).toBe("s1");

    const conversation = await fetch(`${api.url}/api/conversations/s1`);
    expect(conversation.status).toBe(200);
    const messages = (await conversation.json()) as { messages: { role: string }[] };
    expect(messages.messages.length).toBeGreaterThan(0);
  } finally {
    api.close();
  }
});

test("the fixture API refuses every other route", async () => {
  const api = startFixtureApi();
  try {
    const other = await fetch(`${api.url}/api/v1/chat`);
    expect(other.status).toBe(404);
    const body = (await other.json()) as { error: { code: string } };
    expect(body.error.code).toBe("not_found");
  } finally {
    api.close();
  }
});
