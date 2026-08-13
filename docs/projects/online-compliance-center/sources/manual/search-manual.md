# OCC Search — User & Administrator Manual

**Product:** Online Compliance Center (OCC) — Search (eDiscovery workspace)
**Audience:** End users (reviewers, case managers) and administrators
**Scope:** This is a full reference manual. It documents every screen, workflow, field, role, and setting in OCC Search, in the exact wording used by the application.

> This manual describes the `occ-search` application. Its companion, the main Cloud Portal, is documented separately in [portal-manual.md](./portal-manual.md). Both apps share the same identity system, roles, and permissions — see [README.md](./README.md) for the shared model.

---

## Table of contents

1. [Introduction](#1-introduction)
2. [Getting started](#2-getting-started)
3. [Roles & permissions reference](#3-roles--permissions-reference)
4. [The Cases Hub](#4-the-cases-hub)
5. [Creating & managing cases](#5-creating--managing-cases)
6. [The case workspace](#6-the-case-workspace)
7. [Searching](#7-searching)
8. [Browsing the archive](#8-browsing-the-archive)
9. [Working with results](#9-working-with-results)
10. [Inspecting a message](#10-inspecting-a-message)
11. [Tagging](#11-tagging)
12. [Legal holds](#12-legal-holds)
13. [Exporting](#13-exporting)
14. [The case detail drawer](#14-the-case-detail-drawer)
15. [Administration](#15-administration)
16. [Reference appendices](#16-reference-appendices)
17. [Troubleshooting](#17-troubleshooting)

---

## 1. Introduction

**OCC Search** is the eDiscovery / archive-search workspace of the Online Compliance Center. It lets authorized reviewers and legal teams:

- Organize work into **cases** (custodians, archive locations, date scope, assigned reviewers).
- **Search** archived mailbox data with quick keyword search or a structured **Advanced Search**, and save searches as reusable **criteria**.
- **Browse** the archive folder-by-folder.
- **Preview** individual messages and inspect their full indexed properties and attachments.
- **Tag** messages (individually or in bulk) for review workflows.
- Apply **legal holds** to preserve custodian data.
- **Export** messages as EML or MBOX archives.

It searches a cloud search index built from your organization's archived data, and it stores its work (cases, tags, holds, saved searches, exports) in your tenant's compliance service.

**What you can see and do depends on your role and permissions.** Features simply hide or disable when you lack the permission for them. To even enter OCC Search you must hold `cases.read`; without it you see the **"Access not enabled yet"** page.

> **Two "Search" experiences — which one is this?** The official **User Guide – Search (April 2025)** documents the **end-user archive Search**: a webmail-style viewer where a user opens their *own* archived mailbox (and their deputy's), searches it, saves messages to PDF, and forwards them. This manual documents the newer **case-based eDiscovery workspace** (`occ-search`) aimed at reviewers and legal teams, organized around **cases**, **custodians**, **tags**, **legal holds**, and **exports**. Both are branded "Search". Where a concept from the User Guide maps onto — or differs from — this app, a *Reconciliation note* explains it, and [§16.6](#166-reconciliation-with-the-user-guide-april-2025) summarizes all of them.

---

## 2. Getting started

### 2.1 Signing in

1. Open OCC Search. Unauthenticated visitors are sent to `/sign-in`, headed **"Sign in to OCC Search"**.
2. Enter your **Email** (validated as an email address) and **Password** (at least 6 characters), then click **Sign in** (**"Signing in…"**).
3. Depending on your account:
   - **No MFA enrolled** → you're signed straight in.
   - **MFA enabled** → you're taken to the verification page (see [§2.2](#22-two-factor-authentication)).
   - **MFA required but not yet set up** → you're taken to **"Finish setting up two-factor authentication"** (see [§2.3](#23-first-time-mfa-setup)).

Sign-in errors: **"Invalid email or password."**, **"Can't reach the server right now…"**, or **"Sign in failed."** Help text: *"Trouble signing in? Contact your tenant administrator or the OCC support desk."*

> **Reconciliation note (User Guide, April 2025).** The archive Search is reached via a **dedicated link**. From inside the customer's network, sign-in is handled by your **Windows/network login (Single Sign-On via ADFS)** — you usually don't see a login screen at all. From outside, you enter the **same username and password you use for Windows**. Depending on your permissions and license, you may then choose between **Archive**, **eDiscovery**, and (for revision/oversight) **Audit** — regular users are placed straight into **Archive**. The current `occ-search` app instead uses email + password with authenticator-app MFA and opens on the **Cases** hub; if your organization uses SSO/ADFS, follow the User Guide's sign-in instead.

### 2.2 Two-factor authentication

Route: `/mfa-verify`. Headed **"Enter your authentication code"** — *"Open your authenticator app and enter the 6-digit code for OCC Search."*

- Enter the 6-digit **Authentication code** and click **Verify code** (**"Verifying…"**).
- Lost your authenticator? Choose **"Use a recovery code instead"**, then enter a recovery code under **"Enter a recovery code"** (*"Use one of the recovery codes you saved when you set up two-factor authentication."*). Switch back with **"Use an authenticator code instead."**
- Errors: **"Invalid or expired code. Please try again."** / **"Invalid recovery code. Please try again."**

Using a recovery code sends you to re-enrollment (see next section).

### 2.3 First-time MFA setup

Route: `/mfa-setup-required`. Headed **"Finish setting up two-factor authentication"** — *"Your account does not have two-factor authentication set up yet…"* Click **"Open the main portal"** to enroll in the Cloud Portal, then return and sign in to OCC Search. (If the portal address isn't configured, you'll see a note to contact your administrator.)

### 2.4 Session behavior

- Your session (access + refresh tokens and identity) is stored locally and survives closing the tab.
- The app refreshes your access token automatically ~60 seconds before it expires, and again on demand if a request comes back unauthorized.
- **Cross-tab sync:** signing out in one browser tab signs you out everywhere; signing in syncs across tabs.
- **Idle logout:** after a period of inactivity you'll be warned — *"You've been inactive for a while. You'll be signed out in 30 seconds unless you continue."* Any click, keypress, or mouse movement keeps you signed in.

### 2.5 If you don't have access

If your account lacks `cases.read`, you'll see **"Access not enabled yet"** — *"Your account {email} doesn't have access to OCC Search yet…"* Ask an administrator to grant you a role that includes search access.

---

## 3. Roles & permissions reference

OCC Search uses the **same role model as the Cloud Portal** (see [portal-manual §3](./portal-manual.md#3-roles--permissions-reference)). The roles most relevant here are:

- **Client Search Reviewer** — read-only search access; browse, search, preview, and (where granted) tag.
- **Search Manager** — full search domain across the tenant's cases: create/edit/delete cases and criteria.
- **Client Manager** / **Client Administrator** / **System Administrator** / **Super Administrator** — progressively broader administration, including user/role management and (for Client Administrator and above) the four‑eyes toggle.

**Search-relevant permissions** (features hide or disable based on these):

- **Cases:** `cases.read` *(required to enter the app)*, `cases.create`, `cases.update`, `cases.delete`
- **Assignments:** `assignments.read`, `assignments.create`, `assignments.delete`
- **Criteria (saved searches):** `criteria.read`, `criteria.create`, `criteria.update`, `criteria.delete`
- **Search & browse:** `search.execute`, `search.browse`
- **Tags:** `tags.read`, `tags.assign`, `tags.manage`
- **Exports:** `exports.read`, `exports.create`, `exports.download`, `exports.delete`
- **Legal holds:** `holds.create`, `holds.read`, `holds.release`, `holds.retry`; **case-holds:** `case-holds.read`, `case-holds.create`, `case-holds.delete`
- **Audit:** `audit-logs.read`

When you lack a permission, the corresponding tab, button, or action is hidden or disabled (often with an explanatory tooltip, e.g. *"You don't have permission to save criteria"*). No error dialogs are shown for missing permissions.

---

## 4. The Cases Hub

Route: `/cases` (also the default landing page). Titled **"Cases"**.

The hub lists every case you can access in a table with columns:

| Column | Meaning |
|---|---|
| **Case** | Case name (click to open). |
| **Status** | **Open**, **Closed**, or **Archived**. |
| **Created by** | Who created the case. |
| **Created** | Creation date. |
| **Updated** | Last-updated time. |
| **Expires on** | Optional expiry date. |

- **Quick search:** the box **"Search cases by name or description…"** filters the list client-side by name and description.
- **Default sort:** newest first (by Created, descending).
- **Per-case actions** (permission-gated): **Open case**, **Edit case**, **Delete archived case**, and **Change case status** (**Reopen case** / **Close case** / **Archive case**).
- Case cards also show custodian, archive, and hold counts, reviewers, and *"created by {name}"*.
- **Empty states:** *"No cases yet"*, *"No cases assigned"*, or *"No cases match those filters."*

**Case statuses and what they allow:**
- **Open** — full functionality.
- **Closed** — read-only review: *"Search execution, tagging, and saved criteria changes are disabled. Re-open the case to continue reviewing."* Use **Re-open** to resume.
- **Archived** — fully read-only: *"This case is read-only. Browsing and viewing are available; everything else is locked."* Archived is terminal.

---

## 5. Creating & managing cases

### 5.1 Create a case (the New eDiscovery Case wizard)

Requires `cases.create`. The wizard is titled **"New eDiscovery Case"** and has four steps:

**Step 1 — General**
- **Case name** — required. *"A short, memorable title. Visible in the case hub and on all audit entries."* (e.g. *"Project Aurora — Whistleblower review"*).
- **Case description** — optional, searchable. *"Context for reviewers & auditors."*

**Step 2 — Case Details**
- **Date range start** — *"Earliest message date to include in this case. Optional."*
- **Date range end** — *"Latest message date to include in this case. Optional."* (End must not precede start.)
- **Auto-close after** — *"The case is closed automatically this long after it's created."*

**Step 3 — Data Selection**
- **Locations** — *"Archive locations available for this tenant to search."*
- **Custodians** — *"Mailboxes and OneDrive users discoverable in this tenant."*
- **Four‑eyes trigger:** if any selected location is **sensitive/protected**, advancing opens the **"Approval required"** dialog instead of continuing (see [§15.1](#151-four-eyes-approval-for-sensitive-cases)).

**Step 4 — Case Cooperation**
- **Assign case managers** — *"Owners accountable for the case. Users with the Search Manager role."*
- **Assign reviewers** — *"Browse, search, and tag the case's messages. Users with the Search Reviewer role."*

Click **Create case** (**"Creating…"**). On success you return to the hub with *"Case "{name}" created."* (Assignments are best-effort — a failed assignment doesn't undo case creation.)

### 5.2 Edit a case

Requires `cases.update`. Open the edit dialog from a case card or the detail drawer's edit button. All wizard fields are editable. Selecting a sensitive location again triggers the four‑eyes approval flow. Success: *"Case "{name}" updated."* Archived cases are read-only and cannot be edited.

### 5.3 Delete a case

Requires `cases.delete`. A case must be **Archived** first. The confirmation dialog (*"Delete case permanently"*) shows the case's stats and requires ticking **"I understand this action can't be undone."** Success: *"Case "{name}" deleted."*

### 5.4 Change status

Use **Change case status** to move a case between **Open**, **Closed**, and **Archived** (Archived is terminal). See [§4](#4-the-cases-hub) for what each status allows.

---

## 6. The case workspace

Open a case (`/cases/{caseId}`) to enter its workspace — a three-pane layout:

1. **Left — Mailbox tree:** browse custodians and folders (see [§8](#8-browsing-the-archive)).
2. **Center — Message grid:** the current search results or folder contents (see [§9](#9-working-with-results)).
3. **Right — Preview:** the selected message's body and properties (see [§10](#10-inspecting-a-message)).

The panes are resizable. At the top is a **tab bar** and a **quick search** box.

### 6.1 Tabs: Search vs Browse

The workspace opens with a **Search** tab and a **Browse** tab. You can add more:
- **New search** — a tab whose results come from a saved criterion or a free-text query.
- **Browse** — a tab whose results come from the folder you select in the mailbox tree.

Open a new tab with the **"+"** control (choose **New search** or **Browse**); rename a tab with **Rename**; close one with **Close tab**.

**Clean-slate semantics:** tabs are rebuilt fresh every time you open a case. Your folder selection, current page, sort, quick-filter text, and open preview are **not** remembered across reloads or case switches — each visit starts clean.

> **Reconciliation note (User Guide, April 2025).** The archive Search supports **cross-tab (progressive) searches**: opening a new **"Suche" (Search)** tab with **"+"** *keeps the results of the previous search*, so you can run a further search **on top of** the already-filtered set and narrow repeatedly until you find what you need. In this app each search tab is defined by its own criteria/keywords rather than automatically inheriting the previous tab's result set; to narrow, refine the criteria (add more fields in Advanced Search) rather than chaining tabs.

---

## 7. Searching

### 7.1 Quick search

The top-bar **"Quick search…"** box searches your archived data by keyword. To use it:
1. Click into the **"Quick search…"** box on a Search or Browse tab.
2. Type your keyword(s). The search runs automatically as you type (debounced ~300 ms) — on a **Search** tab it runs the query (combined with the tab's saved criteria, if any); on a **Browse** tab it filters the current folder's contents.
3. Read the result count in the tab header (**"{matches} / {total} hits"**) and open any row to preview it.

For structured, multi-field queries, click **Advanced** (see [§7.2](#72-advanced-search)).

> **Reconciliation note (User Guide, April 2025).** The archive Search offers an **"Automatic Search"** toggle: it auto-runs the search as soon as you make a selection. You can **turn it off** so the preview only refreshes when you explicitly ask — useful when you're building a query from several criteria and don't want it running after every change. In this app, quick search is debounced (runs shortly after you stop typing); to assemble a multi-criteria query without repeated runs, compose it in **Advanced Search** and run it once with **Search**.

### 7.2 Advanced Search

The **"Advanced search"** dialog (titled **"Edit criterion"** when editing a saved search) builds a structured query across two tabs. A live **"Query preview"** shows the resulting Azure AI Search expression as you edit. Each field is optional and only contributes when filled in.

**Message tab:**
- **Subject matches** — *"Match the subject line of archived messages."*
- **Sender matches** — *"Match the sender display name or email address."*
- **Any Recipient (To, Cc, Bcc) matches** — *"Match any recipient across the To, Cc, and Bcc fields."*
- **Sent / Received date range** — *"Filter by the envelope Sent or Received timestamp."*
- **Item types** — restrict to one or more of: **Mail**, **Appointment**, **Task**, **Note**.
- **Folders** — restrict to specific folders. Pick from standard folders (Archive, Clutter, Conflicts, Conversation History, Deleted Items, Drafts, Inbox, Junk Email, Local Failures, Notes, Outbox, Recoverable Items Deletions, Scheduled, Search Folders, Sent Items, Server Failures, Sync Issues) or type a custom path (*"Folder name or path (e.g. Deletions, Projects/2024)"*) and click **Add folder**.
- **Tags** — *"Match items carrying any of the selected case tags."* (Search the case's tags.)

**Attachment tab:**
- **Attachment name matches** — *"Match the original attachment filename."* (glob patterns like `invoice*.pdf` supported).
- **File types** — restrict to: **PDF**, **Word**, **Excel**, **PowerPoint**, **Image**, **Other**.

> **Subject match modes** — the engine supports **Word Root match** (default; language stemming), **Phrase match** (case-insensitive phrase, no stemming), and **Exact match** (case-insensitive exact). The selector for these is currently hidden in the UI; **Word Root** is used by default.

**Dialog buttons:**
- **Clear** — reset the criteria.
- **Cancel** — close without searching.
- **Search** (**"Searching…"**) — run the query and open a new search tab. In edit mode this becomes **Save changes** (**"Saving…"**).

When disabled you'll see a tooltip explaining why: *"Add at least one criterion"*, *"This case is not open — search is disabled"*, or *"This case is not open — editing is disabled."*

### 7.3 Saving, loading & editing criteria

- **Save a search:** running Advanced Search persists the criteria to the case as a named criterion (the name is auto-generated from the first non-empty field). Saving requires `criteria.create`.
- **Load a saved criterion:** from the case detail drawer's **Criteria** tab (or the Saved criteria panel), click a criterion to **re-run it in a new search tab**.
- **Edit a criterion:** open it in Advanced Search, refine, and click **Save changes** to overwrite (requires `criteria.update`).
- **Delete a criterion:** from the Criteria list; a confirmation warns it permanently deletes the saved search from the case (requires `criteria.delete`).

Saved criteria are scoped to their case: *"Saved searches are scoped to this case. Re-run any from here or save a new one from Advanced search."*

### 7.4 Search syntax & operators

When you type keywords in the free-text search box, the engine follows these rules:

- **Multiple words = AND.** Entering `Bedürfnisse gelöscht bereinigt` finds items containing **all three** words — not necessarily together — anywhere in the message header (**subject, sender, recipient**) and the **body**. (The Boolean **AND** is applied across the terms.)
- **Phrase search = quotes.** To match an exact phrase, wrap it in double quotes: `"Bedürfnisse gelöscht bereinigt"` matches only where those words appear together in that order.
- **Boolean operators.** The engine supports nearly all Boolean operators, including **AND**, **OR**, **NOT**, **BUT**, and **NEAR** (proximity), plus the **`+`** (must include) and **`-`** (must exclude) symbols.
- **Scope the terms.** Using **Advanced Search** you can direct keywords at a specific field only — e.g. just the **Subject** or just the **Body** — and combine them with a **sender/recipient** and a **date range**.

> The **Query preview** in Advanced Search shows the exact expression that will be sent to the search engine, so you can confirm how your criteria were interpreted before running them.

---

## 8. Browsing the archive

The left-pane **Mailbox** tree lets you browse instead of search.

- **Container types** at the root: **Mailbox**, **Calendar**, **Contacts**, **Tasks**, **Notes** (one set per custodian).
- **"All Custodians"** — a synthetic root that unscopes the view to search the whole case across all custodians.
- **Folders** expand on demand; each shows an item **count** when greater than zero. Standard folders match the list in [§7.2](#72-advanced-search).
- Selecting a folder filters the message grid to that folder's contents; selecting **All Custodians** returns case-wide results.
- Status messages while loading: *"Loading mailbox…"*; on failure *"Failed to load mailbox."* with a retry option; if nothing is in scope: *"No mailbox nodes are in scope for this case."*

A **breadcrumb trail** above the message grid shows your position (e.g. `Mailbox > Inbox > 2024`).

> **Reconciliation note (User Guide, April 2025).** In the archive Search, the left column shows the **folder structure of your own archived mailbox** plus every **location** made visible to you. A regular user normally sees **only their own archive data and their deputy's (Vertreter)**. **Empty folders and not-yet-archived items are hidden.** Archived **calendars, notes, contacts, and tasks** appear alongside mail. Your personal mailbox is archived to you; **shared folders are archived under the data owner**. In this case-based app the equivalent scoping is defined by the case's **custodians** and **archive locations** rather than by your personal mailbox — you browse the custodians in scope for the case (see also proxy/deputy access in [§16.6](#166-reconciliation-with-the-user-guide-april-2025)).

---

## 9. Working with results

The center **message grid** shows the current results.

**Columns:** **From**, **Subject**, **Parent Folder**, **Tags**, **Date**, **Sent / Received**, and **Actions** (**Open preview** / **View details**).

- **Sortable columns:** From, Subject, Date, Sent/Received.
- **Pagination:** page sizes **25 / 50 / 100 / 200** (default **100**).
- **Selection:** tick the checkboxes to select messages (supports select-all/exclude). Selecting rows reveals a bulk action bar: **"{count} message(s) selected"** with **Add tags**, **Export…**, and **Clear selection**. Clicking a row selects it for **preview**; the Actions button opens the preview.
- **Hit count:** each search tab's header shows **"{matches} / {total} hits"** (e.g. *"42 / 150 hits"*).

> **Non-exportable items:** calendar events and tasks can't be exported. If your selection includes them you'll see: *"Selection includes {count} item(s) (tasks or events) that can't be exported — export is unavailable."*

---

## 10. Inspecting a message

Open a message to see the **preview dialog**. Navigate between messages with the **Previous (←)** / **Next (→)** arrows (or the keyboard arrows); a position indicator shows **"{index} / {total}"**.

**Preview tab** (default):
- The message body rendered from sanitized HTML.
- Metadata: **Tags**, **From**, **To**, **Cc**, **Bcc**, **Received**, and **Attachments · {count}**.
- Empty body shows *"(empty message body)"*; unsupported item types show *"No preview for this item type"* — *"This item doesn't have a viewable body. Here are its details."*
- Attachments are listed with download links (short-lived download URLs).

**Properties tab:**
- The full indexed document from the search index, as a read-only key/value table. Fields include: Message id, Item id, Parent id, Item type, Source type, Subject, From, To, Cc, Bcc, Created/Sent/Received/Modified dates, Size, Content type, Importance, Read (YES/NO), Draft (YES/NO), Has attachments (YES/NO), Attachments, File name, Mailbox id, Owner id, Tenant id, Internet message id, Conversation id, Web URL, Fragment id, Archived, Archived date, Archive location, and Tags.
- Loading/errors: *"Loading properties…"*, *"Failed to load properties."*, or *"This message is missing an index key…"*

> **Reconciliation note (User Guide, April 2025) — saving & forwarding single messages.** The archive Search lets an end user act on an individual archived email:
> - **Save to PDF / Print:** open the email so the preview is expanded and readable, click **"Drucken" (Print)**, choose filters, and the email is rendered as a **PDF** in a pop-up that you can **save locally or print**.
> - **Forward:** click **"Weiterleiten" (Forward)** in the preview — because the archive stores items **immutably**, this sends a copy of the archived email **to your own live mailbox**, where you work with it as usual.
>
> This case-based app doesn't provide per-message PDF/print or forward-to-mailbox; instead you preserve and take out messages in bulk via **Legal holds** ([§12](#12-legal-holds)) and **Export** to EML/MBOX ([§13](#13-exporting)).

---

## 11. Tagging

Tags are non-destructive labels applied to messages within a case (they're associations, not edits to the message).

### 11.1 Managing tag definitions
Requires `tags.manage`.
- **Create a tag:** **"Create a tag"** — **Name** (required, ≤ 32 characters), **Color**, and **Description (optional)**. A live **Preview** shows the chip. Click **Create tag** (**"Creating…"**). Success: *"Tag "{name}" created."*
- **Edit a tag:** **"Update tag"** — change name/color/description. Success: *"Tag "{name}" updated."*
- **Delete a tag:** confirmation warns *"This will permanently delete the tag from this case and strip it from every message it's been applied to."* Success: *"Tag "{name}" deleted."*

### 11.2 Applying & removing tags
Requires `tags.assign`.
- **Single message:** use the tag control on a message row or in the preview to add/remove tags.
- **Bulk:** select messages, click **Add tags**. The **"Update tags on selection"** dialog shows every case tag with **Apply** / **Remove** badges — click a tag to toggle its state (*"Click a tag to add it or remove it"*), then **Apply changes** (**"Applying…"**). You can also **Create custom tag** inline and apply it immediately. Footer shows pending counts or *"Nothing to do — selection already matches."* Results: *"Applied {tag} to {count} message(s)."* / *"Removed {tag} from {count} message(s)."*

### 11.3 Filtering by tag
In Advanced Search, the **Tags** field matches messages carrying **any** of the selected tags.

---

## 12. Legal holds

Legal holds preserve custodian data while a case is active. Managed from the case detail drawer's holds panel.

### 12.1 Apply a hold
Requires `holds.create` + `case-holds.create`. The **"Apply legal hold"** dialog:
- **Name** — e.g. *"Aurora — Custodian Hold."*
- **Source** — the root node to preserve (*"Custodian roots scoped to this case."*).
- **Hold type** — *"Where the preservation is applied":*
  - **In Archive** — *"Prevent deletion from the archive only."*
  - **In Place** — *"Preserve in the source mailbox (Exchange/M365)."*
  - **Both** — *"Preserve everywhere."*

Click **Apply hold**. Success: *"Hold "{name}" applied."*

### 12.2 Hold status & lifecycle
Holds show a status badge:
- **Active** — in effect.
- **Released** — lifted (soft; no data purged). Metadata shows *" · Released {date}."*
- **Failed** — the hold could not be applied.

Actions per hold (permission-gated):
- **Release hold** (requires `holds.release`) → *"Hold released."*
- **Retry hold** (requires `holds.retry`, shown when Failed) → *"Hold reactivated."*

The panel summarizes *"{count} hold(s) associated with this case."* Empty state: *"No legal holds applied"* — *"Apply a hold to preserve custodian data while this case is active."* Multiple holds per case are supported.

---

## 13. Exporting

Export produces a downloadable archive of messages. Requires `exports.create`.

### 13.1 Start an export
Two entry points:
- **Bulk export:** select messages in the grid → **Export…** → the dialog is headed **"Export selection"** (eyebrow *"Bulk export · {count} message(s)"*).
- **Full export:** from a search tab, use **Export all** → **"Export full search"** (eyebrow *"Full export · {count} message(s)"*).

**Dialog options:**
- **Archive format:**
  - **EML archive** — *"ZIP of one .eml file per message. Universal RFC-5322 — opens in any mail client."*
  - **MBOX archive** — *"ZIP of mbox mailbox files. Imports into Thunderbird, Apple Mail, and most clients."*
- **Include attachments** — checked by default.
- **Archive password** — optional. *"Leave blank for an unprotected ZIP. The password is never stored — share it with recipients out-of-band."* (Toggle **Show password** / **Hide password**.)

A notice reminds you: *"Calendar events and tasks can't be represented as email, so they're excluded from this export — only messages are included."*

Click **Export {format}** (**"Preparing…"**). On success: *"Export requested — your archive is being prepared."* and a toast *"{format} export requested ({count} message(s))."* If it errors, use **Retry export**.

### 13.2 Track, download & delete exports
Exports appear in the case detail drawer's **Exports** tab, newest first. Each export shows a format, item progress (*"{done} / {total} items"*), and a status:
- **Pending** — queued.
- **Processing** — in progress.
- **Ready** — click **Download** (a short-lived download link is generated).
- **Failed** — the job errored.

Use the **Refresh** button to update statuses. **Delete** removes an export:
- If still preparing: *"This export is still being prepared. Deleting it cancels the job — any work in progress is discarded."*
- If completed: *"This will permanently delete this export and its downloadable archive. Anyone with the link will no longer be able to download it."*

Downloading requires `exports.read`/`exports.download`; deleting requires `exports.delete`.

---

## 14. The case detail drawer

A right-side drawer (eyebrow **"Case details"**) opened from a case or via `/cases/{caseId}/details`. Its tabs appear based on your permissions:

| Tab | Requires | Contents |
|---|---|---|
| **Overview** | (always) | Case metadata: status, date scope (*"Open-ended"*, *"From/Until {date}"*), archive locations, custodians, item types, created by/on, last updated. |
| **Criteria** | `criteria.read` | Saved searches — re-run, edit, or delete each. |
| **Tags** | `tags.read` | The case's tag definitions — create/edit/delete. |
| **Exports** | `exports.read` | Export jobs with status, progress, download, delete, and refresh. |
| **Audit** | `audit-logs.read` | The case audit log (see [§15.2](#152-reviewing-the-audit-log)). |

Header controls: **Edit case** (tooltip explains when disabled — *"You don't have permission to edit cases"* or *"Archived cases are read-only"*), **Refresh** (*"Refreshing from server…"*), and **Close drawer**.

---

## 15. Administration

### 15.1 Four-eyes approval for sensitive cases

When a case includes a **protected (sensitive) archive location**, creating (or editing) it requires administrator approval.

1. In the case wizard's **Data Selection** step, selecting a sensitive location and advancing opens **"Approval required"** — *"This case includes a protected (sensitive) location. Creating it requires approval from an administrator…"*
2. Choose an **Approver** (*"Select an administrator"*) and the **Email language** (English/German), then **Request approval** (**"Sending…"**). You'll see *"Approval request sent"* — *"The approver will receive an email. Once they approve, you'll get a link to come back and finish creating the case."*
3. **Approver** opens the emailed link (`/four-eyes/approve`), headed **"Case creation approval"** (or *"Case change approval"* for edits): *"{requester} would like to create the case "{caseName}" … which includes the protected location "{location}"."* They click **Approve** or **Deny**.
   - Approved: *"Approved. The requester has been notified and can now create the case."*
   - Denied: *"Denied. The requester has been notified."*
4. **Requester** returns via their link (`/four-eyes/resume`): *"Confirming approval…"* then a banner *"Approved — review and create the case "{caseName}"."* Finish creating the case. If the link is stale: *"This link is no longer available. Please request approval again."*

### 15.2 Reviewing the audit log

The **Audit** tab (requires `audit-logs.read`) shows an immutable activity log for the case. Filter by **action**, **resource**, and a **From/To** date range, and use **Load older entries** to page back. Empty result: *"No audit entries match"* — *"Try widening the filters or date range."*

### 15.3 Assignments

Case managers and reviewers are assigned during case creation ([§5.1](#51-create-a-case-the-new-ediscovery-case-wizard)) and can be adjusted by editing the case. Assignment management requires `assignments.create` / `assignments.delete`.

---

## 16. Reference appendices

### 16.1 Route map

**Public:** `/sign-in`, `/mfa-verify`, `/mfa-setup-required`, `/four-eyes/approve`.
**Authenticated:** `/` (→ `/cases`), `/cases`, `/cases/{caseId}`, `/cases/{caseId}/details`, `/four-eyes/resume`. Any unknown authenticated path redirects to `/cases`.

### 16.2 What can be searched

- **Item types:** Mail, Appointment, Task, Note.
- **Fields:** subject, sender, recipients (To/Cc/Bcc), body keywords, item type, date ranges (sent/received), attachment name & type, folder path, tags.
- **Scope:** every search is bounded by the case's custodians, archive locations, and date range.

### 16.3 Search index & sorting

The archive is indexed in **Azure AI Search** (default index name `dg-search-light-index`). Indexed fields surfaced in the Properties tab include `uniqueKey`, `parentId`, `subject`, `fromAddress`, `toRecipients`, `sentDateTime`, `receivedDateTime`, `createdDateTime`, `lastModifiedDateTime`, `size`, `itemType`, `hasAttachments`, `importance`, `contentType`, `mailboxId`, `ownerId`, `tenantId`, `internetMessageId`, `conversationId`, `archived`, `archiveLocation`, `tags`, `webUrl`, and `fragmentId`. Sortable columns in the grid are **From**, **Subject**, **Date** (created), and **Sent/Received** (received).

### 16.4 Configuration (for administrators/operators)

Deployment configuration is managed by your operators and is not exposed to end users. It includes the compliance-service and discovery-service endpoints, the **default tenant ID** used for all tenant-scoped calls, the **search index name**, the **main portal URL** (used by the "finish MFA setup" link), and the data-grid license key. For local demos the app can run against a built-in mock backend with seeded sample data.

### 16.5 Glossary

- **Case** — a container for an investigation: custodians, archive locations, date scope, and assigned reviewers.
- **Custodian** — a person whose mailbox/OneDrive data is in scope.
- **Criterion** — a saved, reusable search.
- **Archive location** — an indexed data source available to search; may be marked *sensitive/protected*.
- **Item type** — mail, appointment, task, or note.
- **Legal hold** — a preservation lock (In Archive / In Place / Both).
- **Deputy (Vertreter)** — a colleague whose archive you're permitted to see alongside your own (archive Search).
- **Proxy access** — a delegated right to view/search another user's archive (see [§16.6](#166-reconciliation-with-the-user-guide-april-2025)).

### 16.6 Reconciliation with the User Guide (April 2025)

The **User Guide – Search** documents the **end-user archive Search**; this manual documents the newer **case-based eDiscovery workspace** (`occ-search`). Where they differ:

| Topic | User Guide (April 2025) | This app (`occ-search`) |
|---|---|---|
| **Purpose** | End user views/searches their **own** archived mailbox | Reviewers work across **cases** (custodians, locations, date scope) |
| **Sign-in** | SSO via **ADFS** internally; username/password (Windows creds) externally | Email + password + authenticator-app MFA |
| **Landing** | Choose **Archive / eDiscovery / Audit**; users default to **Archive** | Opens on the **Cases** hub |
| **Scope** | Your own archive + **deputy's**; shared folders under the data owner | Case **custodians** + **archive locations** |
| **Search entry** | Quick search + Advanced (Message/Attachment) | Same, plus saved **criteria** per case |
| **Progressive search** | New **"Suche" tab keeps previous results** to refine further | Each tab defined by its own criteria; refine by adding criteria |
| **Operators** | AND/OR/NOT/BUT/NEAR, `+`/`-`, quotes for phrase, default AND | Same free-text behavior; **Query preview** shows the expression |
| **Automatic Search** | Toggle to auto-run on selection (can disable) | Quick search is debounced; compose in Advanced Search to run once |
| **Single-message actions** | **Save to PDF / Print** and **Forward to your mailbox** | Not available; use **holds** + **export** (EML/MBOX) instead |
| **Settings** | Preview options, chronological order, time format; language **EN/FR/ES/DE**; open another archive; log out | Language **EN/DE**; personalization is limited; sign out from the top bar |
| **Further/legacy archives** | Access other/legacy archives (**MailStore, REDDOXX, Barracuda**) via delegated **proxy rights** | Modeled as case **custodians/assignments**; proxy rights are configured centrally (see the portal manual's Proxy Rights) |
| **Tags / legal holds / bulk export** | Not documented | Core features ([§11](#11-tagging), [§12](#12-legal-holds), [§13](#13-exporting)) |

> **Proxy / legacy archives.** If you've been delegated access to another mailbox's archive — including old **MailStore / REDDOXX / Barracuda** archives — the archive Search shows those folders under your own start page, and you can view, filter, search, forward, and print them just like your own. In the case-based app, that access is expressed by adding those mailboxes as **custodians** on a case; delegated proxy rights themselves are set up by an administrator (via support) and are documented in the portal manual.

### 16.7 Contact & support

- **Support:** +49 6126 5019 599 · support@sitaas.de
- **Sales / licensing:** +49 6126 5019 500 · sales@sitaas.de
- **Hours:** general Mon–Fri 09:00–17:00; technical hotline Mon–Fri 07:30–18:00 (per your support agreement).
- Purchased via **netmail EMEA GmbH**? Use your netmail contact / netmail Support.

---

## 17. Troubleshooting

- **"Access not enabled yet."** Your account lacks `cases.read`. Ask an administrator to assign you a search role.
- **Stuck on "Finish setting up two-factor authentication."** You must enroll MFA in the Cloud Portal first (**Open the main portal**), then sign in to OCC Search again. If the portal link is missing, contact your administrator.
- **Search/tagging/criteria are disabled.** The case is **Closed** or **Archived**. Re-open it (if Closed) to continue; Archived cases are permanently read-only.
- **No results.** Check the case scope (custodians, locations, date range), your selected folder, and any active quick-filter. Remember the workspace starts clean each visit.
- **"Export is unavailable."** Your selection includes tasks or calendar events, which can't be exported. Deselect them and export only messages.
- **An export never finishes.** Watch its status in the **Exports** tab and use **Refresh**; if it shows **Failed**, start a new export.
- **A legal hold shows "Failed."** Use **Retry hold** to reattempt; if it keeps failing, check that the source/custodian is still in scope.
- **A tab/button/action is missing.** You don't hold the required permission (hover for a tooltip explaining why). Ask an administrator to review your role.
