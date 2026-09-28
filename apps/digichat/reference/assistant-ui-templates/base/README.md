# Xulux Base Assistant UI

A complete chat application built from assistant-ui primitives: thread management, attachments, mentions, slash commands, model picker, and voice input.

## Run

```bash
npm install
npm run dev
```

Add `OPENAI_API_KEY` to `.env.local` for live AI responses. Without a key, `app/api/chat/route.ts` returns a deterministic fallback response so the demo still runs locally. Thread history runs in memory and resets on reload; set `NEXT_PUBLIC_ASSISTANT_BASE_URL` to an assistant-cloud project URL to persist threads and generate titles.

Source demo: `apps/docs/components/pages/examples/base.tsx`
