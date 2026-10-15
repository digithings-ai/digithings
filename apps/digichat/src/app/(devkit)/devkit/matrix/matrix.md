# devkit look x mode matrix

Checked against the devkit workbench at `http://127.0.0.1:4030/devkit`
(headless Chrome, 1440x900, each frame shot from
`[data-testid="devkit-preview-frame"]`).

Six looks x three presentation modes. The generated PNGs are not in the
tree: nothing in the app loaded them, and this note was the only link.

| look | config | modes checked |
|---|---|---|
| default client looks | `local-app.yaml` | app, modal, embed |
| occ | `examples/occ-embed.yaml` (`hosts.occ.digithings.ai`) | app, modal, embed |
| datatap | `examples/datatap-mcp.yaml` | app, modal, embed |
| digichat | `examples/digithings-ai-embed.yaml` (`hosts.digithings.ai`) | app, modal, embed |
| pop-up banner | `examples/dashboard-modal.yaml` | app, modal, embed |
| digichat cli | `examples/local-cli.yaml` | app, modal, embed |

## How each frame was verified

The driver asserted, per cell, that the option it clicked selected the
expected config (`[data-preview-slug]`), that the mode button it clicked set
`data-mode` on the frame to the same value, and that the PNG was non-empty
(25 074 - 62 566 bytes across the 18). Zero uncaught page errors. The three
byte counts inside a row differed, so the mode switch changed the chrome
rather than repainting a label.
