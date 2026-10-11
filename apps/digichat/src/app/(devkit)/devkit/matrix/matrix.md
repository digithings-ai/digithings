# devkit look x mode matrix

Generated against the devkit workbench at `http://127.0.0.1:4030/devkit`
(headless Chrome, 1440x900, each frame shot from
`[data-testid="devkit-preview-frame"]`).

Six looks x three presentation modes = 18 frames, all rendering.

| look | config | fullscreen (`app`) | pop-up (`modal`) | embedded (`embed`) |
|---|---|---|---|---|
| default client looks | `local-app.yaml` | [full](./default-client-looks--fullscreen.png) | [pop-up](./default-client-looks--popup.png) | [embedded](./default-client-looks--embedded.png) |
| occ | `examples/occ-embed.yaml` (`hosts.occ.digithings.ai`) | [full](./occ--fullscreen.png) | [pop-up](./occ--popup.png) | [embedded](./occ--embedded.png) |
| datatap | `examples/datatap-mcp.yaml` | [full](./datatap--fullscreen.png) | [pop-up](./datatap--popup.png) | [embedded](./datatap--embedded.png) |
| digichat | `examples/digithings-ai-embed.yaml` (`hosts.digithings.ai`) | [full](./digichat--fullscreen.png) | [pop-up](./digichat--popup.png) | [embedded](./digichat--embedded.png) |
| pop-up banner | `examples/dashboard-modal.yaml` | [full](./pop-up-banner--fullscreen.png) | [pop-up](./pop-up-banner--popup.png) | [embedded](./pop-up-banner--embedded.png) |
| digichat cli | `examples/local-cli.yaml` | [full](./digichat-cli--fullscreen.png) | [pop-up](./digichat-cli--popup.png) | [embedded](./digichat-cli--embedded.png) |

## How each frame was verified

The driver asserted, per cell, that the option it clicked selected the
expected config (`[data-preview-slug]`), that the mode button it clicked set
`data-mode` on the frame to the same value, and that the PNG is non-empty
(25 074 - 62 566 bytes across the 18). Zero uncaught page errors. The three
byte counts inside a row differ, so the mode switch changes the chrome rather
than repainting a label.

## Why the shots are in the repo

The brief's deliverable is the matrix itself, so the frames travel with the
PR. They are 18 dev-only PNGs in one folder and are trivially removable in
review.
