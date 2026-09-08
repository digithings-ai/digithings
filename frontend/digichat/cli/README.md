# digichat CLI (Ink)

TTY client for the same digichat BFF as the web embed (`POST /api/chat`).
Uses the official assistant-ui **React Ink Terminal Assistant** primitives
(`examples/with-react-ink`) — **not** imported by the Next.js app.

Live mode: `useChatRuntime` + `AssistantChatTransport` (absolute `/api/chat` URL).
`--demo`: the hosted starter’s scripted coding-agent adapter (no backend).

## Run

```bash
cd frontend/digichat/cli
npm install
npm run dev -- --url http://127.0.0.1:3005 --config ../config/examples/local-cli.yaml --embed-token "$TOKEN"
```

Official starter look-and-feel, no BFF:

```bash
npm run dev -- --demo
```

`DIGICHAT_CONFIG` / `--config` fail closed unless `cli.enabled: true` in the YAML.
Without a config path, the binary still runs (YAML is advisory for operators who skip `--config`).
