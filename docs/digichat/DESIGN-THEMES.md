# digichat design themes (ideas)

Status: **ideas only** — not implemented on this branch.

## design.md on vanilla web

Future installs may ship an optional `design.md` (or equivalent token sheet)
that restyles the **stock assistant-ui vanilla Thread** used on digithings embeds
and first-party app chrome. The web surface stays the same component tree
(`ProductStockShell` → vanilla `Thread`); theme input only changes CSS / tokens.

## Website scrape → design.md (later)

Generating `design.md` from a client marketing site (colors, type, radii) needs
a **trusted** scrape/API at deploy time — out of scope until that API exists.
Do not implement scrape-at-deploy in digichat without an explicit trusted
endpoint and human gate.

## Not in scope

- Using Ink / `@assistant-ui/react-ink` as a website or `/embed` look
- Porting CliThread / `session.css` back onto `/embed`
- Digi product names in CamelCase — always lowercase in prose (`digichat`,
  `digigraph`, `digithings`, …)
