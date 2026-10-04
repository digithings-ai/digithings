# BRAND.md

## Name Rule

- **Name:** `digithings` — always one word, always lowercase.
- **Never:** `DigiThings`, `Digithings`, `Digi Things`, `digIthings`, or any CamelCase/snake_case variation.
- **Code identifiers:** Language-idiomatic symbols keep their language's casing (e.g. `DigiChatSession`, `requireDigiChatAuth()`), but *prose, docs, and agent instructions* always use `digithings` lowercase.
- **Exception — code only:** `Digi` may appear as a prefix in TypeScript/React component PascalCase names, Python class names, or HTTP header literals. These are not prose and must not be "fixed" to lowercase in docs or comments.

## Voice

- **Tone:** technical, precise, minimally verbal. Avoid marketing fluff.
- **Tagline:** *"An open-core agentic stack."*
- **No capitalization shifts:** Sentence case, title case, or ALL CAPS are not the digithings voice. When a heading or label needs sentence case, use sentence case consistently — but prefer all-lowercase labels wherever possible.
- **Numeric ranges:** Use `"1.2.3"` format (lowercase, quoted), not `v1.2.3` or `Version 1.2.3`.
- **Issue/PR references:** Use `issue #42` or `PR #1877`, never `#42` alone or `#PR1877`.

## Typography

- **Primary font:** `Geist Mono` for code/mono use, `Geist Sans` for display/sans-serif.
- **Secondary font:** `JetBrains Mono` as a fallback mono; `system-ui, -apple-system, sans-serif` as the fallthrough.
- **Type scale (redesign):** The type ladder is the canonical scale — see `packages/design/tokens.css` for `--type-hero`, `--type-page-title`, `--type-section`, `--type-body`, `--type-meta`.
- **Line height:** `--leading-prose: 1.8` for prose body; `--leading-prose-narrow: 1.75` for narrow columns.
- **Measure:** `--measure-prose: 72ch` for optimal line length.
- **Never use:** `Inter` as the default body font on themed surfaces (themed surfaces remap `--font-family` to `--font-sans` = `Geist Mono` under `:root[data-theme]`).

## Color Tokens

The design system uses tokens from `packages/design/tokens.css`. No raw hex colors appear in prose or docs unless explicitly allowed.

**Dark theme (default):**
- `--bg-primary: #121212`
- `--bg-secondary: #0a0a0a`
- `--text-primary: #e6e6e6`
- `--text-secondary: #a3a3a3`
- `--border-color: #2a2a2a`
- `--ink: #ECEEF0`
- `--accent-color: #ffffff` (alias, legacy)

**Light theme:**
- `--bg: #FBFBF9`
- `--surface: #FFFFFF`
- `--ink: #14181B`
- `--accent: #0C7C71` (redesign phosphor teal, light-theme override)

**Accent palette (per-module, dark theme only):**
- `--accent-digraph: #e5b765`
- `--accent-digiquant: #3dd6c4`
- `--accent-research: #6fbf94`
- `--accent-portfolio: #4a8f7b`
- `--accent-execution: #2f7a65`
- `--accent-digisearch: #5aa3c4`
- `--accent-digichat: #e2708a`
- `--accent-digikey: #d97a5a`
- `--accent-digismith: #6fa3a3`
- `--accent-digiclaw: #b87840`
- `--accent-digibase: #9ea0a5`
- `--accent-digistore: #7b7fc7`
- `--accent-digilink: #4fa39b`
- `--accent-digivault: #9d8fc9`

**Accent palette (light theme, deliberately darker for WCAG 4.5:1):**
- `--accent-digraph: #B27C1E`
- `--accent-digiquant: #0E8C7F`
- `--accent-digisearch: #408FB3`
- `--accent-digismith: #5C8F8F`
- `--accent-digibase: #84878D`
- `--accent-digivault: #8D7DC0`
- `--accent-digilink: #47938C`

**The two polarities (background + ink, used for avatars/OG cards):**
| Polarity | Background | Ink |
|----------|-----------|-----|
| dark | `#0A0E0C` | `#ECEEF0` |
| light | `#FBFBF9` | `#14181B` |

**Never use raw hex in prose, comments, or markdown** outside of `BRAND.md` or token files. All UI rendering draws in `currentColor` or resolves tokens from `packages/design/tokens.css`.

## Logo Use

- **Primary mark:** The `d` glyph derived from the favicon tile in `apps/digithings-web/public/favicon-dg.svg`. This is the reduction of the full `digi` lockup.
- **Avatar:** 1024×1024 SVG/PNG with the `d` + block cursor. Dark version on dark UI, light version on light UI.
- **Dark avatar background:** `#0A0E0C`, light avatar background: `#FBFBF9`.
- **Open Graph cards:** 1200×630px, wordmark outlined to paths (not `<text>`), Geist Mono at weight 400, background fills baked in.
- **X (@digithingsai) header:** 1500×500px compact lockup — do not crop the OG `og.png`; use the dedicated `headers/digithings-x-1500x500.{svg,png}` instead.
- **Never apply effects, warps, or color tints** to the mark. The SVG is the source; PNGs are rendered from it.
- **Clearspace:** Minimum 1x the mark height around the logo in all contexts.
- **Do not combine** the digithings mark with other logos or wordmarks without explicit approval.

## Color Token Exceptions (Allowlist)

Keep the allowlist of raw hex colors short and explicit. These are the only places raw hex may appear outside of `packages/design/tokens.css` and `BRAND.md`:

| Token | Hex | Why it is exempt |
|-------|-----|------------------|
| `--accent-digraph` (dark) | `#e5b765` | Brand gold accent, widely used in CTAs |
| `--accent-digiquant` (dark) | `#3dd6c4` | Brand cyan phosphor, core identity |
| `--accent-digigraph` (light) | `#B27C1E` | Light-theme variant of digigraph |
| `--accent-digiquant` (light) | `#0E8C7F` | Light-theme variant of digiquant |
| Avatar backgrounds | `#0A0E0C`, `#FBFBF9` | Explicitly documented in BRAND.md color table |
| OG card assertion | Geist Mono 0.6em advance | Verification in `build-og.py`, not a brand color per se |

**Any raw hex NOT on this list must be reviewed by the brand guardian before being committed.** When in doubt, use a token variable (`var(--token)`) instead of a literal hex.

## dt-gate Brand Check

- The `dt-gate brand` check runs on **every PR** and validates:
  1. No stray `DigiThings` / `Digithings` / CamelCase module names in prose or docs.
  2. Name rule compliance in commit messages, PR titles, and issue bodies.
  3. Color tokens reference `var(--token)` in component CSS, not raw hex.
  4. Logo assets exist in the canonical `packages/brand/` paths.
  5. No raw hex colors outside the allowlist in non-token CSS/TS files.
- **If the check fails often for one agent:** report the pattern to the improvement lead — the agent likely has a systemic misunderstanding of the brand rules.
- **Fix text-only brand issues** yourself through a normal lane S leaf (standard PR pipeline). Anything involving images, deployed sites, or social bios becomes an issue for the planner.

## twelve-x Real Name

- **twelve-x** is part of the same text-policy gate. Any reference to twelve-x's real name must be **reported to Chris immediately**.
- This is not a brand suggestion — it is a text-policy enforcement boundary.