# Reference scan: omarchy.org

- **URL:** https://omarchy.org
- **Product:** Opinionated Linux distro by DHH (“for the age of agents”)
- **Stack (observed):** Static CSS; JetBrains Mono exclusively
- **Last audited:** 2026-08-30
- **Refero Styles:** not present — closest library matches: Modal, Warp (loose)

---

## 1. First impression

Omarchy is **mono-everything utilitarian with personality**. One font (JetBrains Mono), Tokyo-night navy canvas, terminal cyan/blue type, icon-grid CTAs, and a playful product screenshot. The system voice is “this is a machine you operate,” not “this is a SaaS brochure.”

---

## 2. What to steal for digiweb

| Pattern | Omarchy does | Digiweb adopt / adapt / avoid |
|---------|--------------|-------------------------------|
| Mono as the whole voice | JetBrains Mono for body + UI | **Adapt** — already have `terminal` type suite; good for dashboard / digichat |
| Light weight on dark | weight 300 body | **Adopt** for dense dashboards |
| Terminal link colors | Cyan links, blue body | **Avoid** as default brand — keep phosphor teal / ink hierarchy |
| Centered icon CTA grid | Soft rounded blue pills | **Avoid** rounded multi-CTA grids (fights “one loud thing”) |
| Pixel / synthwave hero art | Gradient pixel wordmark + wallpaper | **Avoid** — digiweb rejects nostalgia decoration |
| Opinionated brevity | Short copy, few sections | **Adopt** |

---

## 3. Tokens (observed)

```
--rgb-background-night: 26, 27, 38   /* #1a1b26 */
--rgb-background-storm: 36, 40, 59
--rgb-terminal-blue: 122, 162, 247
--rgb-terminal-cyan: 125, 207, 255
--rgb-terminal-white: 192, 202, 245
--font-family: 'JetBrains Mono', monospace
```

---

## 4. One-line lesson

> One mono face, terminal colours as punctuation, personality in the product shot — not in chrome chrome.
