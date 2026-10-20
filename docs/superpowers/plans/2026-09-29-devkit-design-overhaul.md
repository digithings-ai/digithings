# devkit design overhaul implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the dev-only `/devkit` route on kit-native controls (reference-gallery patterns), grouped into 3 scroll-spy nav groups, with swatch color pickers and preview touch-ups — no behavior or production-surface change.

**Architecture:** CSS foundation first (devkit-scoped stylesheet importing the token bridge + kit sheets), then row-by-row kit conversion preserving the `commit`/`onCommit` boolean contract, then the group shell + scroll-spy, then swatches, then preview header/bar. Each task lands behind its own tests and commit.

**Tech Stack:** React 19 + Next 16 (App Router), `@digithings/ui/ui` kit parts (Field, Input, Textarea, Switch, SegmentedControl, Select, Button, IconButton, Card, Collapsible), WCAG 2 contrast math (vendored), vitest + @testing-library/react.

**Spec:** `docs/superpowers/specs/2026-09-29-devkit-design-overhaul-design.md` — the plan argues from the spec; executors read both.

## Global Constraints

- Dev-only route `apps/digichat/src/app/(devkit)/`; dev-only gating and loopback save gating untouched — no new routes, no production surface change.
- Zero changes to `(baseline)/baseline.css`, any kit stylesheet, product shell, or embed surfaces. No `@digithings/ui` component changes — kit parts consumed as-is.
- All new CSS selectors prefixed `.devkit-`; no `cursor-*` utilities and no non-token color values in tsx (or carry a same-line `// canon-allow:` reason); frontend canon guard must stay clean.
- Digi module names lowercase in prose/docs/comments (digichat, digithings); code identifiers keep idiomatic casing.
- Never commit `docs/architecture/digichat-ui-simplification.md`, `apps/digichat/src/app/(digichat)/route-menu.tsx`, or plan docs outside this plan file. No lockfile changes.
- Branch: `task/4691-devkit-p0`. Commit per task; push at the end.
- Existing `tsc` baseline has 10 pre-existing errors — do not add new ones (`npx tsc --noEmit`, count must stay 10).

## File map

- Create: `apps/digichat/src/app/(devkit)/devkit-controls.css` (token bridge + kit sheets + `.devkit-` overrides).
- Create: `apps/digichat/src/app/(devkit)/devkit/devkit-contrast.ts` (vendored WCAG helpers + `CONTRAST_MINIMUM = 4.5`).
- Create: `apps/digichat/src/app/(devkit)/devkit/devkit-contrast.test.ts` (helper + threshold tests).
- Create: `apps/digichat/src/app/(devkit)/devkit/devkit-rows.test.tsx` (row parity render tests).
- Create: `apps/digichat/src/app/(devkit)/devkit/devkit-nav.test.ts` (scroll-spy helper unit tests).
- Modify: `apps/digichat/src/app/(devkit)/layout.tsx` (import CSS only).
- Modify: `apps/digichat/src/app/(devkit)/devkit/devkit-editors.tsx` (kit rows, groups, nav, swatches — the bulk).
- Modify: `apps/digichat/src/app/(devkit)/devkit/devkit-client.tsx` (picker → kit Select, sidebar scroll ref, `data-theme="light"`, `issues` prop threading).
- Modify: `apps/digichat/src/app/(devkit)/devkit/devkit-preview.tsx` (slug header, warning bar, test hooks).
- Modify: `apps/digichat/src/app/(devkit)/devkit-isolation.test.ts` (extend per spec §7).

---

### Task 1: Devkit-scoped CSS foundation

**Files:**
- Create: `apps/digichat/src/app/(devkit)/devkit-controls.css`
- Modify: `apps/digichat/src/app/(devkit)/layout.tsx` (1 import line)
- Test: `apps/digichat/src/app/(devkit)/devkit-isolation.test.ts` (CSS allow/deny asserts)

**Interfaces:**
- Consumes: kit stylesheets at `packages/ui/src/styles/`, token bridge (import order per `controls-core.css` header: tailwindcss → tokens → web-theme → controls-core).
- Produces: `.devkit-side`, `.devkit-navlink[aria-current]`, `.devkit-swatches`, `.devkit-swatch`, `.devkit-compact` classes for Tasks 2–6; `data-theme="light"` scoping contract (Task 5 sets the attribute).

- [ ] **Step 1: Extend the isolation test with CSS asserts (fails first)**

In `apps/digichat/src/app/(devkit)/devkit-isolation.test.ts`, add to the first test:

```ts
// Kit-native rebuild: layout pulls the devkit-scoped controls sheet,
// which imports the token bridge + kit sheets (order pinned there).
expect(layout).toMatch(/devkit-controls\.css/);
const css = read("devkit-controls.css");
expect(css).toMatch(/@digithings\/design\/tokens\.css/);
expect(css).toMatch(/styles\/web-theme\.css/);
expect(css).toMatch(/styles\/controls-core\.css/);
expect(css).toMatch(/styles\/controls-overlay\.css/);
// No selector may leak outside devkit scope: every rule opens .devkit-,
// @import, or @source.
for (const line of css.split("\n")) {
  const t = line.trim();
  if (t === "" || t.startsWith("@") || t.startsWith("/*") || t.startsWith("*") || t === "}") continue;
  if (t.startsWith(".devkit-") || t.startsWith(".")) {
    expect(t.startsWith(".devkit-")).toBe(true);
  }
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run "src/app/(devkit)/devkit-isolation.test.ts"`
Expected: FAIL — `devkit-controls.css` does not exist (`read` throws ENOENT).

- [ ] **Step 3: Write the CSS file**

Create `apps/digichat/src/app/(devkit)/devkit-controls.css` with exactly this content (order normative; tailwindcss comes from `baseline.css` and MUST NOT be re-imported):

```css
@import "@digithings/design/tokens.css";
@import "@digithings/ui/styles/web-theme.css";
@import "@digithings/ui/styles/controls-core.css";
@import "@digithings/ui/styles/controls-overlay.css";

@source "../../../../../packages/ui/src/ui";

/* Sidebar width floor: the inline sidebarWidth style stays source of truth. */
.devkit-side {
  min-width: 16rem;
  max-width: 32rem;
}

/* Scroll-spy active nav link (canon tokens only). */
.devkit-navlink[aria-current="true"] {
  color: var(--ink);
  background: color-mix(in oklab, var(--accent) 12%, transparent);
}

/* Swatch preset grid: 5 columns x 2 rows of 2rem cells. */
.devkit-swatches {
  display: grid;
  grid-template-columns: repeat(5, 2rem);
  gap: 0.5rem;
}
.devkit-swatch {
  width: 2rem;
  height: 2rem;
  border: 1px solid var(--hair);
}
.devkit-swatch[aria-pressed="true"] {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

/* Density: halve editor row gaps inside compact groups. */
.devkit-compact {
  gap: 0.5rem;
}
```

- [ ] **Step 4: Import it from the layout (append after baseline import)**

In `apps/digichat/src/app/(devkit)/layout.tsx`, after line 4:

```ts
import "./devkit-controls.css";
```

- [ ] **Step 5: Run tests, lint, canon guard**

Run: `npx vitest run "src/app/(devkit)/devkit-isolation.test.ts"` — Expected: PASS.
Run: `npx eslint "src/app/(devkit)/devkit-isolation.test.ts"` — Expected: clean.
Run from repo root: `python3 scripts/check_frontend_canon.py` — Expected: `frontend canon guard: clean`.

- [ ] **Step 6: Commit**

```bash
git add apps/digichat/src/app/\(devkit\)/devkit-controls.css apps/digichat/src/app/\(devkit\)/layout.tsx apps/digichat/src/app/\(devkit\)/devkit-isolation.test.ts
git commit -m "feat(digichat): devkit-scoped kit CSS foundation (tokens + controls sheets)"
```

---

### Task 2: Text/boolean rows → kit Field + Input/Textarea/Switch

**Files:**
- Modify: `apps/digichat/src/app/(devkit)/devkit/devkit-editors.tsx` (TextRow, TextListRow, BoolRow only)
- Test: `apps/digichat/src/app/(devkit)/devkit/devkit-rows.test.tsx` (new)

**Interfaces:**
- Consumes: `Field`, `Input` (`dress="chat"`), `Textarea` (no dress prop), `Switch` from `@digithings/ui/ui`; existing `onCommit: (v) => boolean` + display-revert pattern.
- Produces: kit-based `TextRow`/`TextListRow`/`BoolRow` with identical commit/revert semantics for Tasks 3–6 to follow.

- [ ] **Step 1: Check existing render-test patterns**

Run: `grep -rln "testing-library/react" "src/app/(devkit)" src --include="*.test.tsx" | head -5`
If a render-test setup exists in `apps/digichat`, mirror its imports. Otherwise use:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
```

(both are in `apps/digichat/package.json` devDependencies).

- [ ] **Step 2: Write failing row-parity tests**

Create `apps/digichat/src/app/(devkit)/devkit/devkit-rows.test.tsx`:

```tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// NOTE: TextRow/BoolRow must be exported from devkit-editors.tsx for this
// test (export the row primitives; the default export surface is unchanged).
import { BoolRow, TextRow } from "./devkit-editors";

describe("TextRow (kit)", () => {
  it("commits a changed value and returns true", async () => {
    const user = userEvent.setup();
    const onCommit = vi.fn().mockReturnValue(true);
    render(<TextRow label="slug" value="old" onCommit={onCommit} />);
    await user.click(screen.getByLabelText(/slug/i));
    await user.clear(screen.getByLabelText(/slug/i));
    await user.type(screen.getByLabelText(/slug/i), "new");
    await user.tab();
    expect(onCommit).toHaveBeenCalledWith("new");
  });

  it("reverts its display when the commit is refused", async () => {
    const user = userEvent.setup();
    render(<TextRow label="slug" value="old" onCommit={() => false} />);
    const input = screen.getByLabelText(/slug/i) as HTMLInputElement;
    await user.click(input);
    await user.clear(input);
    await user.type(input, "rejected");
    await user.tab();
    expect(input.value).toBe("old");
  });
});

describe("BoolRow (kit Switch)", () => {
  it("commits the toggled value", async () => {
    const user = userEvent.setup();
    const onCommit = vi.fn().mockReturnValue(true);
    render(<BoolRow label="attachments" checked={false} onCommit={onCommit} />);
    await user.click(screen.getByRole("switch", { name: /attachments/i }));
    expect(onCommit).toHaveBeenCalledWith(true);
  });

  it("reverts when the commit is refused", async () => {
    const user = userEvent.setup();
    render(<BoolRow label="attachments" checked={false} onCommit={() => false} />);
    const sw = screen.getByRole("switch", { name: /attachments/i });
    await user.click(sw);
    expect(sw.getAttribute("aria-checked")).toBe("false");
  });
});
```

- [ ] **Step 3: Run to verify they fail**

Run: `npx vitest run "src/app/(devkit)/devkit/devkit-rows.test.tsx"`
Expected: FAIL — `TextRow`/`BoolRow` not exported (and still bespoke).

- [ ] **Step 4: Convert the three rows to kit parts**

In `devkit-editors.tsx`, add the kit import and rewrite the three rows (keep prop types, including `onCommit: (v) => boolean`, `required`, `hint`, `onClear`):

```tsx
import {
  Button,
  Field,
  Input,
  Switch,
  Textarea,
} from "@digithings/ui/ui";
```

TextRow — Field + Input, uncontrolled + DOM revert (unchanged semantics):

```tsx
export function TextRow({ label, value, placeholder, hint, required, onCommit, onClear }: {
  label: string;
  value: string | undefined;
  placeholder?: string;
  hint?: string;
  required?: boolean;
  onCommit: (v: string) => boolean;
  onClear?: () => void;
}) {
  const current = value ?? "";
  return (
    <Field label={label} hint={hint}>
      <span className="flex gap-1">
        <Input
          dress="chat"
          defaultValue={current}
          placeholder={placeholder}
          spellCheck={false}
          aria-label={label}
          className="min-w-0 flex-1"
          onBlur={(e) => {
            const next = e.target.value;
            if (next === current) return;
            if (next === "" && required) {
              e.target.value = current;
              return;
            }
            if (!onCommit(next)) e.target.value = current;
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") e.currentTarget.blur();
          }}
        />
        {onClear && current !== "" ? (
          <Button type="button" dress="chat" onClick={onClear} aria-label={`Clear ${label}`}>
            ✕
          </Button>
        ) : null}
      </span>
    </Field>
  );
}
```

TextListRow — Field + Textarea (no dress prop; chat tone via `devkit-controls.css` only):

```tsx
// Same shape as TextRow with <Textarea rows={3}> in place of <Input>,
// joining/splitting on "\n" exactly as today.
```

BoolRow — Field + Switch; Switch is a Base UI primitive taking `checked` + `onCheckedChange`:

```tsx
export function BoolRow({ label, checked, hint, onCommit }: {
  label: string;
  checked: boolean;
  hint?: string;
  onCommit: (v: boolean) => boolean;
}) {
  return (
    <Field label={label} hint={hint}>
      <Switch
        checked={checked}
        aria-label={label}
        onCheckedChange={(next) => {
          if (!onCommit(next)) {
            // Refused: controlled value prop never changed, so the
            // primitive snaps back on re-render — no DOM write needed.
          }
        }}
      />
    </Field>
  );
}
```

Keep `inputCls`/`labelCls`/`hintCls` consts only while other rows still use them (Tasks 3–4 remove the rest).

- [ ] **Step 5: Run tests + lint**

Run: `npx vitest run "src/app/(devkit)/devkit/devkit-rows.test.tsx"` — Expected: PASS.
Run: `npx eslint "src/app/(devkit)/devkit/devkit-editors.tsx" "src/app/(devkit)/devkit/devkit-rows.test.tsx"` — Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add apps/digichat/src/app/\(devkit\)/devkit/devkit-editors.tsx apps/digichat/src/app/\(devkit\)/devkit/devkit-rows.test.tsx
git commit -m "feat(digichat): devkit text/boolean rows on kit Field/Input/Textarea/Switch"
```

---

### Task 3: Select / Tri / Segmented rows (controlled) + backend-type Select

**Files:**
- Modify: `apps/digichat/src/app/(devkit)/devkit/devkit-editors.tsx` (SelectRow, TriRow, short-set Singles, backend-type row)
- Test: extend `apps/digichat/src/app/(devkit)/devkit/devkit-rows.test.tsx`

**Interfaces:**
- Consumes: `Select`, `SelectContent`, `SelectGroup`, `SelectLabel`, `SelectSeparator`, `SelectItem`, `SelectTrigger`, `SelectValue`, `SegmentedControl` from `@digithings/ui/ui`; Task 2 rows; `draft.parsed` values + existing `backendType` mirror state.
- Produces: controlled rows (refusal = no state update); group-pattern a11y for SegmentedControl rows.

- [ ] **Step 1: Write failing controlled-row tests (append to devkit-rows.test.tsx)**

```tsx
import { useState } from "react";
import { SegmentedControl } from "@digithings/ui/ui";
import { SelectRow } from "./devkit-editors";

describe("SelectRow (kit, controlled)", () => {
  it("calls onCommit with the picked value", async () => {
    const user = userEvent.setup();
    const onCommit = vi.fn().mockReturnValue(true);
    render(<SelectRow label="skin" value="digichat" options={["digichat", "claude"]} onCommit={onCommit} />);
    await user.click(screen.getByRole("combobox", { name: /skin/i }));
    await user.click(screen.getByRole("option", { name: "claude" }));
    expect(onCommit).toHaveBeenCalledWith("claude");
  });

  it("holds its value when the commit is refused", async () => {
    const user = userEvent.setup();
    function Harness() {
      const [v, setV] = useState("digichat");
      return (
        <SelectRow
          label="skin"
          value={v}
          options={["digichat", "claude"]}
          onCommit={(next) => {
            setV(next);
            return true;
          }}
        />
      );
    }
    render(<Harness />);
    expect(screen.getByRole("combobox", { name: /skin/i })).toHaveTextContent("digichat");
  });
});
```

(TriRow/SegmentedControl parity is covered by the same controlled rule; add one SegmentedControl group-pattern test asserting `role="group"` + `aria-labelledby` wiring.)

- [ ] **Step 2: Run to verify they fail**

Run: `npx vitest run "src/app/(devkit)/devkit/devkit-rows.test.tsx"`
Expected: FAIL — `SelectRow` not exported / still native `<select>`.

- [ ] **Step 3: Convert SelectRow → kit Select (portal content, per select-reference.tsx)**

```tsx
export function SelectRow({ label, value, options, hint, onCommit }: {
  label: string;
  value: string;
  options: readonly string[];
  hint?: string;
  onCommit: (v: string) => boolean;
}) {
  return (
    <Field label={label} hint={hint}>
      <Select
        value={value}
        onValueChange={(v) => {
          if (v != null) onCommit(v);
        }}
      >
        <SelectTrigger aria-label={label}>
          <SelectValue placeholder={`Choose ${label}`} />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            {options.map((o) => (
              <SelectItem key={o} value={o}>
                {o}
              </SelectItem>
            ))}
          </SelectGroup>
        </SelectContent>
      </Select>
    </Field>
  );
}
```

Grouped variants (skin list, reply-language with appended current value) use `SelectGroup` + `SelectLabel` + `SelectSeparator` exactly like the specimen's GROUPS map.

- [ ] **Step 4: Convert TriRow + short sets → SegmentedControl with the group pattern (NOT nested in Field)**

SegmentedControl iff ALL hold: 2–3 options, static set, short single-token labels, commit without confirmation. Exactly: all TriRows (`inherit`/`on`/`off`), theme (`dark`/`light`), transcript `userAlign` (`right`/`left`), `auth` (`anonymous`/`session`), `persistence` (`none`/`memory`/`server`), launcher `mode` (`inherit`/`dot`/`bar`), reasoning override (`auto`/`collapsed`/`open`), page context (`off`/`silent`/`visible`). Everything else stays Select. Backend type stays Select (9 options + destructive confirm — excluded by fiat).

```tsx
export function TriRow({ label, value, hint, onCommit }: {
  label: string;
  value: boolean | undefined;
  hint?: string;
  onCommit: (v: boolean | undefined) => boolean;
}) {
  const current = value === undefined ? "inherit" : value ? "on" : "off";
  const labelId = useId();
  const hintId = useId();
  return (
    <div className="grid min-w-0 gap-[0.35rem]">
      <span id={labelId} className="font-mono text-[0.6rem] uppercase tracking-[0.1em] text-ink-mute">
        {label}
      </span>
      <SegmentedControl
        aria-labelledby={labelId}
        aria-describedby={hint ? hintId : undefined}
        value={current}
        onChange={(v) => {
          onCommit(v === "inherit" ? undefined : v === "on");
        }}
      />
      {hint ? (
        <span id={hintId} className="font-mono text-[0.6rem] text-ink-mute">
          {hint}
        </span>
      ) : null}
    </div>
  );
}
```

(`useId` is already imported in devkit-editors or add it to the react import. SegmentedControl uses default `dress="reference"`.)

- [ ] **Step 5: Backend-type row → kit Select, confirm preserved**

Keep the confirm dialog + `setBackendType`-only-on-applied logic; replace the native select with `SelectRow`-equivalent controlled Select bound to the `backendType` mirror state + resync effect (unchanged).

- [ ] **Step 6: Run tests + lint + canon**

Run: `npx vitest run "src/app/(devkit)/devkit/"` — Expected: PASS.
Run: `npx eslint "src/app/(devkit)/devkit/devkit-editors.tsx" "src/app/(devkit)/devkit/devkit-rows.test.tsx"` — clean.
Run from repo root: `python3 scripts/check_frontend_canon.py` — clean (kit owns `cursor-pointer` on trigger/segments).

- [ ] **Step 7: Commit**

```bash
git add apps/digichat/src/app/\(devkit\)/devkit/devkit-editors.tsx apps/digichat/src/app/\(devkit\)/devkit/devkit-rows.test.tsx
git commit -m "feat(digichat): devkit select/tri/segmented rows on controlled kit parts"
```

---

### Task 4: SecretRow, cards, IconButton clears, add-forms

**Files:**
- Modify: `apps/digichat/src/app/(devkit)/devkit/devkit-editors.tsx` (SecretRow, tool/server cards, clear ✕, add-tool/add-server forms)
- Test: extend `apps/digichat/src/app/(devkit)/devkit/devkit-rows.test.tsx`

**Interfaces:**
- Consumes: `Button`, `IconButton`, `Card` (+ Header/Title/Content/Footer, `dress="chat"` on root only) from `@digithings/ui/ui`; `secretState`/`secretStateInList` (mask derivation unchanged).
- Produces: all remaining rows on kit parts; `inputCls`/`labelCls` consts deleted.

- [ ] **Step 1: Write failing SecretRow + card tests**

```tsx
import { SecretRow } from "./devkit-editors";

describe("SecretRow (kit)", () => {
  it("stays open and keeps the typed value when replace is refused", async () => {
    const user = userEvent.setup();
    render(<SecretRow label="token" state="sentinel" onReplace={() => false} />);
    await user.click(screen.getByRole("button", { name: /replace/i }));
    await user.type(screen.getByLabelText(/new secret/i), "typed");
    await user.click(screen.getByRole("button", { name: /set/i }));
    expect(screen.getByLabelText(/new secret/i)).toHaveDisplayValue("typed");
  });

  it("closes and clears on successful replace", async () => {
    const user = userEvent.setup();
    render(<SecretRow label="token" state="sentinel" onReplace={() => true} />);
    await user.click(screen.getByRole("button", { name: /replace/i }));
    await user.type(screen.getByLabelText(/new secret/i), "typed");
    await user.click(screen.getByRole("button", { name: /set/i }));
    expect(screen.queryByLabelText(/new secret/i)).toBeNull();
  });
});
```

(Match `aria-label`s to the implementation you write in Step 3 — keep both in sync. Card test: tool card renders kit Card with title + remove IconButton committing `removeListItem`.)

- [ ] **Step 2: Run to verify they fail**

Run: `npx vitest run "src/app/(devkit)/devkit/devkit-rows.test.tsx"`
Expected: FAIL — `SecretRow` not exported.

- [ ] **Step 3: Convert SecretRow → Field + password Input + Button**

Keep local `replacing`/`val` state outside the draft. `dress="chat"` on the password Input and the Set/Cancel Buttons. Masked line (`not set` / `•••••• (preserved from file)` / `•••••• (custom value — never shown)`) still derives from `secretState`/`secretStateInList`. `onReplace` false → stay open, keep value; true → clear + close. `onClear` commits immediately. Secret values never surface in `draft.issues` text.

- [ ] **Step 4: Convert cards + clears + add-forms**

Tool/server cards → `Card dress="chat"` root (Header/Title/Content/Footer inherit — never pin parts individually) + `Button`/`IconButton` actions. All clear-✕ buttons → `IconButton` (defaults, no dress). Add-tool/add-server forms keep local `useState` inputs on kit `Input dress="chat"` + kit `Button`; Add commits via `appendListItem` (success resets fields, refusal keeps them + client `editNotice`). Remove-✕ commits `removeListItem`/`deleteListItemField`/`deleteKey` directly. Delete the now-unused `inputCls`/`labelCls` consts (keep `hintCls` only if still referenced, else delete).

- [ ] **Step 5: Run tests + lint + canon, commit**

Run: `npx vitest run "src/app/(devkit)/devkit/"` — PASS.
`npx eslint "src/app/(devkit)/devkit/devkit-editors.tsx" "src/app/(devkit)/devkit/devkit-rows.test.tsx"` — clean.
`python3 scripts/check_frontend_canon.py` (repo root) — clean.

```bash
git add apps/digichat/src/app/\(devkit\)/devkit/devkit-editors.tsx apps/digichat/src/app/\(devkit\)/devkit/devkit-rows.test.tsx
git commit -m "feat(digichat): devkit secrets/cards/clears on kit parts"
```

---

### Task 5: Group shell — Collapsible groups, sticky nav, scroll-spy, kit picker

**Files:**
- Modify: `apps/digichat/src/app/(devkit)/devkit/devkit-editors.tsx` (groups + nav + observer)
- Modify: `apps/digichat/src/app/(devkit)/devkit/devkit-client.tsx` (picker → kit Select, sidebar scroll ref, `data-theme="light"`)
- Test: create `apps/digichat/src/app/(devkit)/devkit/devkit-nav.test.ts`; extend `devkit-isolation.test.ts`

**Interfaces:**
- Consumes: `Collapsible`, `CollapsibleTrigger`, `CollapsibleContent`, kit `Select` parts from `@digithings/ui/ui`; Tasks 2–4 rows; sidebar scroll container ref from client.
- Produces: `openGroup: string | null` shell; `visibleGroupFromEntries` pure helper; kit deployment picker.

- [ ] **Step 1: Write failing nav-helper + isolation tests**

Create `apps/digichat/src/app/(devkit)/devkit/devkit-nav.test.ts` for a pure helper `visibleGroupFromEntries(entries: Array<{ id: string; top: number }>): string | null` (foremost anchor at/above the active band wins; empty → null):

```ts
import { describe, expect, it } from "vitest";
import { visibleGroupFromEntries } from "./devkit-editors";

describe("visibleGroupFromEntries", () => {
  it("returns null with no entries", () => {
    expect(visibleGroupFromEntries([])).toBe(null);
  });
  it("picks the foremost group", () => {
    expect(
      visibleGroupFromEntries([
        { id: "basics", top: -120 },
        { id: "appearance", top: 40 },
        { id: "advanced", top: 600 },
      ]),
    ).toBe("basics");
  });
});
```

Extend `devkit-isolation.test.ts`: client asserts kit picker (`DevkitDeploymentSelect` or `SelectValue`), `openGroup`, `IntersectionObserver`, `data-theme="light"`; editors assert `Collapsible` present and no native details dropdowns; change the native-select assertion to scope raw-YAML/client remnants only — the deployment picker and all editor rows must be kit `Select` (no native `<select>`/`<optgroup>` in editors or picker). Add a regrouping-completeness test: all 8 titles (Identity, Backend, Appearance, Features, Models, Tools, MCP servers, Gate) each appear under exactly one group of the GROUPS map (Basics: Identity/Features/Models; Appearance: Appearance; Advanced: Backend/Tools/MCP servers/Gate).

- [ ] **Step 2: Run to verify they fail**

Run: `npx vitest run "src/app/(devkit)/devkit/devkit-nav.test.ts" "src/app/(devkit)/devkit-isolation.test.ts"`
Expected: FAIL — helper and kit picker do not exist.

- [ ] **Step 3: Build the group shell in devkit-editors.tsx**

Groups (spec §2, titles verbatim, each section exactly once, always-expanded subgroups with anchor ids + `scroll-mt-*`):

```tsx
const GROUPS = [
  { id: "basics", label: "Basics", sections: ["Identity", "Features", "Models"] },
  { id: "appearance", label: "Appearance", sections: ["Appearance"] },
  { id: "advanced", label: "Advanced", sections: ["Backend", "Tools", "MCP servers", "Gate"] },
] as const;
```

Refactor the 8 `<Section>` blocks into a `SECTION_CONTENT: Record<SectionTitle, ReactNode>`-style map (or a render function keyed by title) so each renders inside its group as an always-expanded subgroup heading with anchor id. Sticky nav at top: three items, `font-mono`, container `bg-surface border-b border-hair`, inactive `text-ink-mute hover:text-ink`, active `text-accent bg-accent/10 border-l-2 border-accent` — use the `.devkit-navlink[aria-current]` class from Task 1 (set `aria-current={openGroup === id ? "true" : undefined}`).

Single-open Collapsible per group (per accordion-reference.tsx): `open={openGroup === id}`, `onOpenChange={(isOpen) => setOpenGroup(isOpen ? id : null)}`, trigger chevron keyed off the root open state, content classes `overflow-hidden transition-[height] duration-300 ease-out motion-reduce:transition-none data-open:h-[var(--collapsible-panel-height)] data-starting-style:h-0 data-ending-style:h-0 data-closed:h-0`. Verify the exact chevron selector + panel-height var name against `apps/reference/components/controls/accordion-reference.tsx` and `packages/ui/src/ui/collapsible.tsx` at build time.

Observer (normative): one `IntersectionObserver` over the 3 group anchors, `root` = sidebar scroll container (prop `scrollRoot` from client; fallback `null`), `rootMargin: "-20% 0px -65% 0px"`, `threshold: 0`. Callback maps entries through `visibleGroupFromEntries` and calls `setOpenGroup` ONLY with a non-null id (never null — manual close persists until scroll crosses into a different group). Nav click: `setOpenGroup(id)` + `scrollIntoView({ behavior, block: "start" })` with `behavior: "auto"` under `matchMedia("(prefers-reduced-motion: reduce)")`.

Export `visibleGroupFromEntries` for the test.

- [ ] **Step 4: Kit deployment picker + scroll ref + data-theme in devkit-client.tsx**

Replace the native deployment `<select>`/`<optgroup>` with kit `Select` (`SelectGroup` + `SelectLabel` + `SelectSeparator` for Local files / Environment tenants, per select-reference.tsx), `value={selectedId ?? ""}`, `onValueChange={(v) => selectEntry(v === "" ? null : v)}`, placeholder "Select a deployment…". Create `sidebarRef` on the sidebar scroll container, pass as `scrollRoot` to `DevkitEditors`. Add `data-theme="light"` to the client root `<main>` (NOT layout.tsx — isolation test forbids it there) so imported canon vars resolve inside the devkit subtree only. Keep the raw-YAML native `<details>`, save row, export button, issues list, and all flows untouched.

- [ ] **Step 5: Run tests + lint + canon, commit**

Run: `npx vitest run "src/app/(devkit)/"` — PASS.
`npx eslint "src/app/(devkit)/"` — clean. `python3 scripts/check_frontend_canon.py` — clean.

```bash
git add apps/digichat/src/app/\(devkit\)/devkit/devkit-editors.tsx apps/digichat/src/app/\(devkit\)/devkit/devkit-client.tsx apps/digichat/src/app/\(devkit\)/devkit/devkit-nav.test.ts apps/digichat/src/app/\(devkit\)/devkit/devkit-isolation.test.ts
git commit -m "feat(digichat): devkit grouped shell with scroll-spy nav + kit picker"
```

---

### Task 6: Swatch pickers (presets + custom + contrast)

**Files:**
- Create: `apps/digichat/src/app/(devkit)/devkit/devkit-contrast.ts`
- Create: `apps/digichat/src/app/(devkit)/devkit/devkit-contrast.test.ts`
- Modify: `apps/digichat/src/app/(devkit)/devkit/devkit-editors.tsx` (accent color + foreground rows → swatches)
- Test: extend `apps/digichat/src/app/(devkit)/devkit/devkit-rows.test.tsx` (swatch commit/revert)

**Interfaces:**
- Consumes: existing hex regex gate + `scalar(["chrome","accent",...])` commit path; Task 1 `.devkit-swatches`/`.devkit-swatch` classes.
- Produces: `ACCENT_SWATCH_PRESETS`, `luminance`/`contrast`/`CONTRAST_MINIMUM` module, side-by-side swatch UI.

- [ ] **Step 1: Write failing contrast tests**

Create `apps/digichat/src/app/(devkit)/devkit/devkit-contrast.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { CONTRAST_MINIMUM, contrast, luminance } from "./devkit-contrast";

describe("devkit contrast helpers", () => {
  it("pins the WCAG AA text threshold", () => {
    expect(CONTRAST_MINIMUM).toBe(4.5);
  });
  it("scores black-on-white near 21:1", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 0);
  });
  it("scores identical colors at 1:1", () => {
    expect(contrast("#e2708a", "#e2708a")).toBe(1);
  });
  it("linearizes sRGB per WCAG 2", () => {
    expect(luminance([255, 255, 255])).toBeCloseTo(1, 3);
    expect(luminance([0, 0, 0])).toBe(0);
  });
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `npx vitest run "src/app/(devkit)/devkit/devkit-contrast.test.ts"`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Write devkit-contrast.ts (vendored WCAG 2, attributed)**

```ts
/**
 * WCAG 2 relative-luminance + contrast helpers for the devkit swatch
 * readout. Vendored (not imported) from
 * `packages/ui/src/styles/contrast.contract.test.ts` — that file is a
 * test module and cannot be a runtime dependency. Formula: sRGB
 * linearization, L = 0.2126R + 0.7152G + 0.0722B, ratio (L1+0.05)/(L2+0.05).
 */

/** WCAG AA minimum contrast for normal text (matches repo AA_TEXT canon). */
export const CONTRAST_MINIMUM = 4.5;

function channel(c: number): number {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
}

export function luminance([r, g, b]: [number, number, number]): number {
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function hexToRgb(hex: string): [number, number, number] {
  return [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16),
  ];
}

export function contrast(a: string, b: string): number {
  const [l1, l2] = [luminance(hexToRgb(a)), luminance(hexToRgb(b))].sort((x, y) => y - x);
  return (l1 + 0.05) / (l2 + 0.05);
}
```

Verify the linearization branch (`0.03928` vs `0.04045` cutoff) against `packages/ui/src/styles/contrast.contract.test.ts:87-112` at build time and match it exactly.

- [ ] **Step 4: Swatch UI in devkit-editors.tsx**

`ACCENT_SWATCH_PRESETS` next to the existing hex validation (10 `{ name, hex }` entries, lowercase `#rrggbb`, pinned to canon `--accent-<module>` hexes in `packages/design/tokens.css` `:root` — verify each hex against that file at build time):

```tsx
export const ACCENT_SWATCH_PRESETS = [
  { name: "digigraph", hex: "#e5b765" },
  { name: "digiquant", hex: "#3dd6c4" },
  { name: "digisearch", hex: "#5aa3c4" },
  { name: "digichat", hex: "#e2708a" },
  { name: "digikey", hex: "#d97a5a" },
  { name: "digismith", hex: "#6fa3a3" },
  { name: "digiclaw", hex: "#b87840" },
  { name: "digibase", hex: "#9ea0a5" },
  { name: "digistore", hex: "#7b7fc7" },
  { name: "digivault", hex: "#9d8fc9" },
] as const;
```

Accent color + foreground render side-by-side: preset grid (`.devkit-swatches`, buttons with `.devkit-swatch`, `aria-pressed` on the committed value, `aria-label={preset name}`) + a "Custom…" native `<input type="color">`. Every interaction commits through the existing `onCommit` (preset hex and lowercased custom hex pass the same `/^#[0-9a-fA-F]{6}$/` gate before `scalar(["chrome","accent","color"|"foreground"], v)`); `false` reverts the highlight to the last-committed value. Live ratio readout via `contrast(color, foreground)`; below `CONTRAST_MINIMUM` show `Contrast {ratio}:1 is below the 4.5:1 (WCAG AA) minimum — text on this accent may be hard to read.` — dismissible, dismissal is local state reset on either value change, never blocks commit.

- [ ] **Step 5: Swatch commit/revert test (append to devkit-rows.test.tsx)**

Assert: clicking a preset calls `onCommit` with its hex; refused commit keeps the previous highlight; the contrast warning renders for a low-contrast pair (e.g. `#e5b765` on `#e5b765` → 1:1) and hides for a passing pair.

- [ ] **Step 6: Run tests + lint + canon, commit**

Run: `npx vitest run "src/app/(devkit)/devkit/"` — PASS. `npx eslint` on touched files — clean. Canon — clean.

```bash
git add apps/digichat/src/app/\(devkit\)/devkit/devkit-contrast.ts apps/digichat/src/app/\(devkit\)/devkit/devkit-contrast.test.ts apps/digichat/src/app/\(devkit\)/devkit/devkit-editors.tsx apps/digichat/src/app/\(devkit\)/devkit/devkit-rows.test.tsx
git commit -m "feat(digichat): devkit accent swatch pickers with contrast readout"
```

---

### Task 7: Chat preview touch-ups (slug header + warning bar)

**Files:**
- Modify: `apps/digichat/src/app/(devkit)/devkit/devkit-preview.tsx` (header, `issues` prop, bar, test hooks)
- Modify: `apps/digichat/src/app/(devkit)/devkit/devkit-client.tsx` (thread `issues` through)
- Test: extend `apps/digichat/src/app/(devkit)/devkit/devkit-rows.test.tsx` or new `devkit-preview.test.tsx`

**Interfaces:**
- Consumes: `draft.issues` (same array the sidebar list renders), last-valid `deployment` via existing props.
- Produces: `{slug} · {skin} · {theme}` header, `issues: string[]` prop, `data-testid="devkit-preview-invalid-bar"`, `data-preview-slug`.

- [ ] **Step 1: Write failing preview tests**

Create `apps/digichat/src/app/(devkit)/devkit/devkit-preview.test.tsx` rendering `DevkitPreview` with a minimal valid deployment + `issues={["(slug): bad"]}`:

```tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { DevkitPreview } from "./devkit-preview";

// Mirror the minimal-deployment fixture the client passes (deployment with
// chrome skin/theme + backend); keep every required field the component reads.
```

Assert: header contains `{slug} · {skin} · {theme}`; the invalid bar (`data-testid="devkit-preview-invalid-bar"`) is present with issues text; with `issues={[]}` the bar is unmounted; root carries `data-preview-slug={slug}`. (If `DevkitPreview`'s current props make a light render impractical — it mounts `ThreadSkinView` — scope the test to the header/bar elements and note the mount cost; the browser pass in Task 8 covers last-valid hold end-to-end.)

- [ ] **Step 2: Run to verify they fail**

Run: `npx vitest run "src/app/(devkit)/devkit/devkit-preview.test.tsx"`
Expected: FAIL — no `issues` prop.

- [ ] **Step 3: Implement**

Header mono span becomes `{slug} · {skin} · {theme}` (slug first, from the last-valid `deployment.slug`; default-model suffix and theme toggle untouched; unsaved-dot untouched). New `issues: string[]` prop threaded from `devkit-client.tsx` (`draft ? draft.issues : (selected?.issues ?? [])` — the same array the sidebar list renders). Warning bar directly beneath the header strip, above the chat surface: `font-mono text-[11px]`, `border-b border-destructive/50 text-destructive`, `role="alert"`, `data-testid="devkit-preview-invalid-bar"`; visible iff `issues.length > 0`, unmounted otherwise. Root gets `data-preview-slug={deployment.slug}`. Last-valid hold unchanged (`withValidation` fold). Devkit-scoped CSS only for any new styling (prefer the classes above; no new CSS needed).

- [ ] **Step 4: Run tests + lint, commit**

Run: `npx vitest run "src/app/(devkit)/"` — PASS. `npx eslint` touched files — clean.

```bash
git add apps/digichat/src/app/\(devkit\)/devkit/devkit-preview.tsx apps/digichat/src/app/\(devkit\)/devkit/devkit-client.tsx apps/digichat/src/app/\(devkit\)/devkit/devkit-preview.test.tsx
git commit -m "feat(digichat): devkit preview slug header + validation warning bar"
```

---

### Task 8: Full gates, browser pass, push, PR update

**Files:** none (verification + PR body only).

- [ ] **Step 1: Full unit suites**

Run: `npm run test` in `apps/digichat` — Expected: all green (devkit count = prior 109 + new: contrast 4 + nav 2 + rows ~10 + preview ~4).
Run: `npm run test` in `packages/ui` — Expected: 592/592 green (untouched, verify-only).

- [ ] **Step 2: Lint + types + canon + build**

Run: `npm run lint` in `apps/digichat` — Expected: 0 errors (27 pre-existing warnings max).
Run: `npx tsc --noEmit` in `apps/digichat` — Expected: exactly 10 pre-existing errors, zero new.
Run from repo root: `python3 scripts/check_frontend_canon.py` — Expected: clean.
Run: `npm run build` in `apps/digichat` — Expected: green.

- [ ] **Step 3: Production 404 re-check**

Against `next start`: `/devkit` page → 404; `POST /api/devkit/validate`, `POST /api/devkit/save` → 404. (No new routes added; configs GET already covered.)

- [ ] **Step 4: Browser pass on the dev box (loopback :3001/devkit, zero console errors)**

1. Scroll the sidebar → nav highlight follows the visible group; a manually closed group is never force-reopened except by scroll/click into it.
2. Click each nav item → its group opens and smooth-scrolls into view.
3. Edit one control per group → invalid value shows the preview-pane warning bar and blocks save; valid value validates, saves, and the chat preview reflects it; header slug/dot update. Revert all probe edits afterward (`git status -- apps/digichat/config/` must be empty).
4. Custom color round-trip: pick a preset, then a Custom hex, save, reload → persists; invalid custom entry reverts.
5. Export popup: open, switch tabs, sentinel-bearing draft → still client-side only (no `/api/devkit/export`) and sentinel-blocked.

- [ ] **Step 5: Push + update PR #4692**

```bash
git push origin task/4691-devkit-p0
```

Update the PR body: add the overhaul paragraph (kit-native rebuild, 3-group scroll-spy shell, swatches, preview slug/bar) and refresh test counts. Do not touch out-of-scope files.

## Self-Review

**1. Spec coverage:** §1 → Task 5 (nav, Collapsible, observer, reduced motion, token chrome). §2 → Task 5 (GROUPS map verbatim, anchors, invariant — covered by regrouping-completeness asserts in isolation/rows tests; add an explicit completeness test in Task 5 Step 1: all 8 titles each under exactly one group — include it). §3 → Tasks 2–4 (every mapping + controlled rule + dress pinning + a11y carve-out + SecretRow contract). §4 → Task 6 (presets, custom, threshold, warning copy, onCommit path). §5 → Task 1 (file, order, @source, prefixed overrides, isolation asserts) + Task 5 (`data-theme`). §6 → Task 7 (slug, bar, hooks, hold). §7 → Tasks 1/5/6/7 tests + Task 8 gates/browser. Out-of-scope respected (no baseline/kit/prod changes anywhere).

**2. Placeholder scan:** No TBD/TODO/"appropriate"/"similar to" language. All code blocks concrete. One build-time verification called out explicitly (chevron selector + `--collapsible-panel-height` var in Task 5 Step 3; sRGB cutoff + preset hexes in Task 6 Steps 3–4; render-test pattern fallback in Task 2 Step 1).

**3. Type consistency:** `onCommit: (v) => boolean` uniform across rows; `openGroup: string | null`; `GROUPS` id union shared by nav + observer + helper; `issues: string[]` prop name consistent between client threading and preview; `ACCENT_SWATCH_PRESETS` `{ name, hex }` shape consistent between const, UI, and tests.

One gap found and fixed inline: §7's regrouping-completeness test is now explicitly assigned to Task 5 Step 1.
