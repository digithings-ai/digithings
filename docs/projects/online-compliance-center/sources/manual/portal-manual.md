# Cloud Portal — User & Administrator Manual

**Product:** Online Compliance Center (OCC) — Cloud Portal
**Audience:** End users and administrators
**Scope:** This is a full reference manual. It documents every screen, workflow, field, role, and setting in the Cloud Portal, in the exact wording used by the application.

> This manual describes the `cloud-portal-ui` application. Its companion, the eDiscovery search workspace, is documented separately in [search-manual.md](./search-manual.md). Both apps share the same identity system, roles, and permissions — see [README.md](./README.md) for the shared model.

---

## Table of contents

1. [Introduction](#1-introduction)
2. [Getting started](#2-getting-started)
3. [Roles & permissions reference](#3-roles--permissions-reference)
4. [The application shell](#4-the-application-shell)
5. [Overview / Online Compliance Center](#5-overview--online-compliance-center)
6. [Backup & Restore](#6-backup--restore)
7. [Data Management (Compliance)](#7-data-management-compliance)
8. [Email Archive & Teams Archive](#8-email-archive--teams-archive)
9. [Account settings](#9-account-settings)
10. [Administration (Configuration)](#10-administration-configuration)
11. [Partner Config & Azure Dashboard](#11-partner-config--azure-dashboard)
12. [Reference appendices](#12-reference-appendices)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. Introduction

The **Cloud Portal** is the main web application of the **Online Compliance Center (OCC)**. It lets organizations protect and govern their Microsoft 365 data:

- **Backup & Restore** — schedule and run backups of Exchange mailboxes, OneDrive accounts, SharePoint sites, and Teams; restore that data when needed.
- **Data Management** — browse and manage file/versioning compliance state across SharePoint and OneDrive.
- **Email Archive & Teams Archive** — compliance archiving, retention, and deletion jobs (delivered through `portal.netmail.cloud` — see [§8](#8-email-archive--teams-archive)).
- **Reporting & documents** — dashboards, exportable reports, and organization documents.
- **Administration** — user, role, tenant, client and announcement management; the four‑eyes (two‑person) approval rule; and audit logs.

The portal is a browser application that connects securely to your organization's Microsoft 365 environment to run backups, restores, and compliance jobs, and to store the resulting data in your tenant's protected cloud storage.

**What you can see and do depends on your role, your permissions, and your tenant's license.** Menu items and buttons appear, disappear, or are greyed out accordingly. See [§3](#3-roles--permissions-reference).

> **A note on names and history.** The Online Compliance Center was known as **netmail cloud** / the **netmail Cloud Portal** from 2019 and was rebranded to **Online Compliance Center** in 2025. It is a product of **sitaas GmbH** in partnership with **netmail EMEA GmbH**. The main production portal is reached at **`https://portal.netmail.cloud`**. This manual documents the current application and, where the current app differs from the official **Admin Guide (Feb 2025)**, calls out the difference in a *Reconciliation note*; a summary of all such differences is in [§12.5](#125-reconciliation-with-the-admin-guide-feb-2025).

---

## 2. Getting started

### 2.1 Signing in

1. Open the portal URL. You land on the sign-in page (`/signin`), headed **"Sign in to your account"**.
2. Enter your **Username** and **Password** (password must be 7–42 characters). Use the eye icon to reveal the password.
3. Click sign in.
   - On success you see **"Welcome! You've successfully signed in."** and are taken to your dashboard (or the page you originally requested).
   - On failure you see **"Invalid Credentials."** or **"Login process failed."**
4. If two-factor authentication (2FA) is enabled for your account, you are routed to code verification (see [§2.4](#24-two-factor-authentication-2fa)).

### 2.2 Activating a new account

New users receive an invitation email with a magic link.

- **Activation page** (`/activate`): set your password (7–42 chars, at least one uppercase letter, and at least one special character), confirm it, and click **Activate account**.
  - Success: **"Your account is now active. Please sign in."**
  - Expired/invalid link: **"This activation link is invalid or has expired"** — *"Ask an administrator to resend your invitation."* Use **Back to login**.
- **Magic-link registration** (`/account/new`): an alternative activation entry point that sets your password from an invitation link.

### 2.3 Forgot / reset password

- **Forgot password** (`/forgot-password`): enter your email. You'll see **"We've sent a verification link to your email…"** (or, depending on configuration, a message that a reset code has been sent).
- **Reset password** (`/reset-password`): open the link (or enter the reset code), then set and confirm a new password under the heading **"Set your password"**.
  - Success: **"Your password has been updated successfully!"**
  - Failure: **"Failed to reset password!"**

### 2.4 Two-factor authentication (2FA)

**First-time setup** (`/qr-setup`):

1. **"Please scan the QR code in order to start the setup."** Install an authenticator app if you don't have one — buttons link to **Microsoft Authenticator** and **Google Authenticator**.
2. Scan the on-screen QR code with your app.
3. Enter the 6-digit code under **"To continue, please enter the code from your authenticator app"** and click **Verify Code**.
4. **Save your recovery code**: **"Please save this recovery code securely. It is your backup for account recovery."** Use **Copy code** (you'll see *"The code has been copied successfully"*). Store it somewhere safe — it's how you recover access if you lose your authenticator.

**Every subsequent login** (`/code-verification`):

1. Enter the 6-digit code from your authenticator in **"Enter the code here"**.
2. If you've lost your authenticator, choose **"Use a recovery code instead"** and enter your recovery code. (You can switch back with **"Use an authenticator code instead"**.)
3. Success: **"The code has been successfully verified."**

**Error handling:**
- Wrong code: **"Invalid Verification Code"** / **"Invalid code. Please try again."**
- Too many wrong codes: **"Too many incorrect codes — your account is locked. Enter your recovery code to unlock; this resets your authenticator app."**
- Used recovery code: **"The recovery code has been used."**

> **Reconciliation note (Admin Guide, Feb 2025).** The official Admin Guide describes multi-factor authentication by **email**: after entering your username and password you receive an automatically generated **6-digit verification code** by email (it expires in **5 minutes**), which you enter and confirm with **Verify**. The current application uses the **authenticator-app (TOTP)** method described above, with recovery codes. Both provide MFA at every login; only the delivery of the code has changed (email code → authenticator app). If your environment still uses email codes, follow the guide's email-code steps instead.

### 2.5 Session timeout

You are automatically signed out after a period of inactivity (the Admin Guide specifies **5 minutes**). Simply sign in again to continue. Your language and other preferences are preserved.

### 2.6 First login

On your first sign-in you may see:

- A **"Welcome to OCC | Online Compliance Center!"** dialog with **Grant Tenant Permissions** / **Set Tenant Permissions**, plus guidance on group setup, notifications, and the Help Center.
- Release announcements badged **"What's new"** — click **Got it** to dismiss.

---

## 3. Roles & permissions reference

Access is governed by three independent layers:

1. **Role** — your job function (assigned by an administrator).
2. **Permissions** — fine-grained capability strings returned for your account at login. Menu items and buttons are shown/hidden based on whether you hold the required permission(s).
3. **License** — your tenant's subscription. A module link is *disabled (greyed out)* when the license is known to exclude that capability. (When the license is missing/unrecognized, links are **not** disabled — permission gating still applies.)

### 3.1 Roles

The built-in roles are:

| Role | Scope | Typical use |
|---|---|---|
| **Super Administrator** | All tenants | Full platform administration; holds every permission (`tenants.access-any`). |
| **System Administrator** | All tenants | Cross-tenant administrator variant with all permissions. |
| **Client Administrator** | One client/tenant | Tenant-level admin; manages users and the four‑eyes rule. One per client. |
| **Client Manager** | One tenant | Functional manager across all four domains + portal read + user/role admin. |
| **Search Manager** | One tenant | eDiscovery/search domain (used in the Search app). |
| **Backup & Restore Manager** | One tenant | Create/manage backup & restore jobs; restore approval eligibility. |
| **Archive Manager** | One tenant | Archive jobs and archive locations. |
| **Data Management Manager** | One tenant | Data-management jobs. |
| **Client System Reviewer** | One tenant | Read-only portal + system data. |
| **Client Search Reviewer** | One tenant | Read-only search access. |
| **Restore Approver** *(capability role)* | — | A second-approver capability held **alongside** a primary role for four‑eyes approvals; not used on its own. |

**Who can assign which roles:**
- **Super / System Administrators** create users from the cross-tenant **User Management** screen and may assign **any** role — including Client Administrator (transferred off any prior holder, one per client) and, deliberately, the Super/System Administrator roles.
- A **Client Administrator** assigns roles from the client-scoped **Users** screen, and may assign every role **except** Super Administrator, System Administrator, and Client Administrator (separation of duties).

### 3.2 Permissions catalogue

Permissions are grouped by domain. UI gating is based on these strings.

- **Scope:** `tenants.access-any`, `tenants.assign`, `cases.access-any`, `cases.access-scope`
- **Users:** `users.list`, `users.create`, `users.read`, `users.update`, `users.delete`, `users.hard-delete`
- **Permission grants:** `permissions.grant`, `permissions.revoke`
- **Roles:** `roles.list`, `roles.create`, `roles.read`, `roles.update`, `roles.delete`, `roles.assign`
- **Cases:** `cases.create`, `cases.read`, `cases.update`, `cases.delete`
- **Assignments:** `assignments.read`, `assignments.create`, `assignments.delete`
- **Search criteria:** `criteria.create`, `criteria.read`, `criteria.update`, `criteria.delete`
- **Search & browse:** `search.execute`, `search.browse`
- **Tags:** `tags.manage`, `tags.read`, `tags.assign`
- **Exports:** `exports.create`, `exports.read`, `exports.download`, `exports.delete`
- **Legal holds:** `holds.create`, `holds.read`, `holds.release`, `holds.retry`; **case-holds:** `case-holds.read`, `case-holds.create`, `case-holds.delete`
- **Clients:** `clients.list`, `clients.create`, `clients.read`, `clients.update`, `clients.delete`, `clients.set-tenant-id`
- **Client files:** `client-files.read`, `client-files.upload`, `client-files.delete`
- **Partnerships:** `partnerships.list/create/read/update/delete`
- **Announcements:** `announcements.list/create/read/update/delete`; **reads:** `announcement-reads.list/create/delete`
- **Audit logs:** `audit-logs.read`
- **Four-eyes:** `four-eyes.create`, `four-eyes.read`, `four-eyes.update`, `four-eyes.approve`, `four-eyes.delete`, `four-eyes.manage`; domain-scoped: `four-eyes.approve.backup`, `four-eyes.approve.search`
- **Restore jobs:** `restore.create` *(the four‑eyes-gated chokepoint)*, `restore.read`, `restore.start`, `restore.stop`
- **Backup jobs:** `backup.create/read/update/delete/start/stop`
- **Archive jobs:** `archive.create/read/update/delete/start/stop`; **locations:** `archive-locations.read/create/update/delete`; **policies:** `archive-policies.read/create/update/delete`
- **Data Management jobs:** `datamgmt.create/read/update/delete/start/stop`
- **Engine locations & credentials:** `locations.read/create/update/delete`, `credentials.read/create/delete`
- **System jobs:** `jobs.system.manage` (admin only)
- **Portal read surface:** `dashboard.read`, `reports.read`, `reports.send`, `sitaas.read`
- **Azure dashboard:** `azure-dashboard.read`, `azure-dashboard.update`

### 3.3 How menu visibility works

Each sidebar entry declares the permission(s) that reveal it; you see the item if you hold **any** of them. Notes:

- **Super Administrator** (`tenants.access-any`) passes every check.
- Admin-only tools — **Hidden Jobs**, **Partner Config**, **Azure Dashboard** — are **hidden entirely** for anyone who lacks access (gated on `tenants.access-any`), rather than shown greyed out.
- Product links are shown but **disabled** when the license excludes them.
- **Account** (Settings/Help/Support) and the **Overview** section are always available to every signed-in role.

---

## 4. The application shell

Once signed in, every page renders inside the main shell:

- **Header** — logo and app name (*"Netmail — Online Compliance Center"*), breadcrumbs of the current page path, a tenant/worker selector (if you have access to more than one tenant), and an account menu with your name, language, and logout.
- **Sidebar** — the primary navigation. Sections expand to reveal sub-pages. Visibility follows the rules in [§3.3](#33-how-menu-visibility-works).

**Sidebar map:**

```
Online Compliance Center (Overview)
  ├─ Dashboard
  ├─ Reports
  └─ Documents
Backup & Restore
  ├─ Dashboard
  ├─ Backup Jobs
  ├─ Restore
  ├─ Job Monitor
  ├─ Reports
  ├─ User Dashboard (License Management)
  └─ Hidden Jobs            (Super/System Admin only — hidden otherwise)
Data Management (Compliance)
  ├─ Dashboard
  ├─ File Manager
  ├─ Job Monitor
  └─ Reports
Archive                     (moved to legacy portal — see §8)
  ├─ Dashboard
  ├─ Jobs / Job Monitor / Reports / User Dashboard   (disabled)
eDiscovery                  (disabled in the portal; links out to the Search app)
Account
  ├─ Settings
  ├─ Help Center            (external)
  └─ Support
Configuration              (admins — appears if you can reach at least one tab)
Partner Config             (Super Admin only — hidden otherwise)
Azure Dashboard            (Super/System Admin only — hidden otherwise)
```

*(A Slack integration section appears only for one specific internal tenant and is not part of the standard product.)*

---

## 5. Overview / Online Compliance Center

Routes: `/` and `/dashboard` (Overview), `/reports`, `/documents`.

### 5.1 Homepage / dashboard

Greets you with **"Welcome to your Online Compliance Center, {your name}"** and an overview of your organization's cloud activity, compliance status, backup status, and monthly reports. It is the launchpad to every module. It surfaces:

- Your active **licenses/modules** and usage.
- **Announcements** ("What's new") until read or expired.
- Navigation shortcuts: **View Dashboard**, **Show Accounts**, **Show Documents**, **Show Reports**.
- A one-click jump into the **eDiscovery** search app.
- Quick access to **Reports**, **Documents**, and **Support**.
- On the last line: your **Organization** and the **Service Availability** figure — the service is provided with a **99.5%** availability commitment.

Your **account menu** (top-right) is available from every page to sign out and to reach Support.

### 5.2 Reports

Organization-wide reports. Read access is open to all roles. The monthly **Cloud Report** is available to download and includes the monthly number of **users & resources**, your **active archive licenses**, and the number of **archived mailboxes, archived messages, and archived attachments**.

### 5.3 Documents

Organization documents (e.g., PDFs) that the OCC team makes available to you — tailored to how your organization uses the platform. Everyone can read/download them; **uploading and deleting** documents requires `client-files.upload` / `client-files.delete` (held by Super/System Administrators).

---

## 6. Backup & Restore

The Backup & Restore module protects four Microsoft 365 **connectors**: **Exchange**, **Teams**, **SharePoint**, and **OneDrive**. Most screens present these as tabs.

**Requires** `backup.read` and/or `restore.read` to appear. Individual links are disabled if your license excludes them (e.g., an *email-only* license disables Teams/SharePoint/OneDrive and the restore surface).

### 6.1 Dashboard

Route: `/backup-and-restore/dashboard`. Shows per-connector metrics and coverage:

- **Exchange** — M365 mailbox count, *"Exchange Mailboxes Backed Up"* (coverage of total), top mailboxes by backup storage, email messages/attachments/accounts in backup.
- **OneDrive** — M365 OneDrive users, users backed up, files in backup, top users by storage.
- **SharePoint** — sites in M365, sites in backup, top sites by storage.
- **Teams** — teams in M365, teams in backup, top teams by storage.
- **Cross-cutting cards** — *"Backup volume · last 12 months"* trend chart, *"Last Successful Backup Job"*, *"Overall coverage"*, *"No Backup for More Than 1 Year"*, and a **License Management** shortcut.

### 6.2 Backup Jobs

Route: `/backup-and-restore/backup-jobs`. At the top of the page are the connector tabs — **Exchange**, **Teams**, **SharePoint**, **OneDrive** (tabs your license doesn't cover are disabled). Each tab shows a table of that connector's backup jobs. For every job the row shows its name, schedule, and last status, with actions:

- **Start** — run the job now (a confirmation dialog appears).
- **Stop** — stop a running job.
- **Edit** — reopen the job in the wizard to change its selection, filters, or schedule.
- **Delete** — remove the job (a confirmation dialog appears).
- **View Report** — open the latest run's report.

To create a job, click **Create Backup Job**. This opens the **Backup Wizard** as a step-by-step flow. At the bottom of the wizard, **Next** advances a step and **Finish** creates the job; you can click a completed step in the stepper to go back. An **Advanced Setup** toggle at the top-right adds a **Filters** step (see [§6.2.5](#625-advanced-filters-advanced-setup)); it is not available to trial users.

The wizard's steps depend on the connector:

| Connector | Steps |
|---|---|
| **Exchange** | 1) General → 2) Mailbox Selection → *(Filters, if Advanced Setup is on)* → 3) Schedule |
| **Teams** | 1) General → 2) Teams Selection → *(Filters)* → 3) Schedule |
| **SharePoint** | 1) General → 2) Sites → *(Filters)* → 3) Schedule |
| **OneDrive** | 1) General → 2) Users → 3) Filters → 4) Schedule |

#### 6.2.1 Step 1 — General (all connectors)

Under **"Job Settings"**:
- **Job Name** — required; must be at least 4 characters.
- **"Microsoft Information Protection (AIP)"** section:
  - **"Backup Sensitivity Labels (In case your organisation is using Microsoft Information Protection)"** — turn this on if your organization uses sensitivity labels and you want them preserved.
  - When you turn AIP on, a dependent option appears indented below it: **"Decrypt protected emails before backup (requires Sensitivity Labels backup to be enabled)."** It follows the AIP switch automatically. If you turn it **off**, a **"Disable Decrypt Protected Emails"** dialog asks you to confirm, because *protected emails will then not be searchable in the search app*. Confirm or cancel.

Click **Next**.

#### 6.2.2 Step 2 — Choosing what to back up

This step differs per connector. In every case you can either pick specific items or let the system include everything automatically.

**Exchange — Mailbox Selection.** This step has two sub-tabs, **Mailboxes** and **Groups** (use one or the other):

- **Mailboxes tab:**
  1. In **"Select one or more Mailboxes"**, search and pick the mailboxes to back up. Each option shows the display name and email address.
  2. Or turn on **"Select all Mailboxes"** to back up every mailbox — including ones added later. A confirmation notes: *"OCC activates the backup automatically for all new Mailboxes in your Microsoft tenant."*
  3. Optionally turn on **"Exclude selected Mailboxes"** to invert your selection — i.e. back up everything *except* the mailboxes you picked. (Available once you've selected at least one mailbox.)
- **Groups tab:**
  1. In **"Select one or more Groups"**, pick security/distribution groups; the job resolves to their member mailboxes.
  2. Turn on **"Select All Groups"** to include all groups, or **"Exclude Selected Groups"** to invert.
  3. After adding a group you can click it to open a dialog and **exclude specific mailboxes** within that group (*"Mailboxes selected here will be excluded from the job"*).

**OneDrive — Users.** Two sub-tabs, **Users** and **Groups**, working exactly like Exchange's:
- **Users tab:** **"Select one or more Users"**, or **"Select all Users"** (*"…automatically for all new Users…"*), or **"Exclude selected Users."**
- **Groups tab:** **"Select one or more Groups"**, **"Select All Groups"**, **"Exclude Selected Groups"**, and per-group member exclusion.

**SharePoint — Sites.** A single **"Sites"** selector:
1. In **"Select one or more Sites"**, pick the SharePoint sites (and team-linked sites) to back up. Each option is marked with a SharePoint or Teams icon.
2. Or turn on **"Select all Sites"** (*"…automatically for all new Sites…"*).
3. Optionally **"Exclude selected Sites"** to invert.

**Teams — Teams Selection.** A single **"Teams Selection"** selector:
1. In **"Select one or more Teams"**, pick the teams to back up (channels, posts, and files are included).
2. Or turn on **"Select all Teams"** (*"…automatically for all new Teams…"*).
3. Optionally **"Exclude selected Teams"** to invert.

Click **Next**.

> **Trial licenses:** the "select all" switches are hidden, and you can select at most **10** mailboxes / users / sites / teams / groups per job.

#### 6.2.3 Step 3 — Schedule (all connectors)

Under **"Job Recurrence"**, choose one option (each is a selectable card):

| Option | Meaning | Extra fields |
|---|---|---|
| **Disabled** | *"No automatic runs."* The job only runs when you press **Start** manually. | — |
| **Start after creation** | *"Runs once immediately."* Runs one time as soon as it's created. | — |
| **Daily** | *"Every day at a set time."* | **Execution Time** — pick the hour/minute (**Select Hour**). |
| **Weekly** | *"Selected days at a set time."* | **Execution Time** + **Days of the Week** (pick one or more days). |

**Scheduling conflict guard:** times within **±1 hour** of another of your scheduled jobs are blocked in the time picker, and choosing a clashing time shows *"This time conflicts with another scheduled job (±1 hour)."* Pick a different time or day.

#### 6.2.4 Finishing

Click **Finish**. On success you'll see **"Successfully created new Job!"** (or *"The job has been created successfully."*).
- If you chose **Start after creation**, *"The job will start in a few moments! You can monitor it on the Job Monitor page."*
- Otherwise the job waits: it runs when the schedule fires, or when you press **Start** on the Backup Jobs table if scheduling is **Disabled**.

> **Four‑eyes:** when the two-person rule is enabled, sensitive job creation must be approved by a second authorized person before it takes effect — see [§10.2](#102-four-eyes-two-person-approval).

#### 6.2.5 Advanced filters (Advanced Setup)

Turning on **Advanced Setup** (top-right of the wizard) inserts a **Filters** step before Schedule. It lets you narrow exactly what each job captures. At the top you choose the overall strategy:

- **Include** — the items you list here are the *only* ones processed.
- **Exclude** — everything is processed *except* the items you list.

You can then specify (each as a list, with separate Include/Exclude entries):
- **Paths** — folder paths to include/exclude.
- **Mime Types** — content types to include/exclude (the list is tailored per connector; for Exchange these can be set to **"Apply to Attachments Only"**).
- **Email Subject** (Exchange) / **Item Names** (other connectors) — match by subject or item name.
- **Extensions** — file extensions to include/exclude.
- **Aip Labels** — sensitivity labels to include/exclude.
- **Date After** / **Date Before** — restrict to items within a date range.

**OneDrive** always shows a simpler dedicated **Filters** step (even without Advanced Setup): **Excluded File Extensions** (choose from **TXT**, **PDF**, **EXE**) and **Filter by Date** (**Date After** / **Date Before**).

#### 6.2.6 Managing existing backup jobs

On the **Backup Jobs** table (per connector tab) the action icons let you:

- **Start (green play):** clicking opens a confirmation pop-up — click **Yes, confirm** to run the job now, or **Cancel** to close. This is how you run jobs whose schedule is **Disabled**.
- **Delete (red trash):** opens a confirmation pop-up; **Yes, confirm** deletes the job. A green notification confirms *"The job has been successfully deleted!"*
- **Edit (blue pencil):** reopens the wizard. Click through **General**, **Account Selection**, **Filters**, and **Schedule** to change what you need (for example, adjusting the run time). Changes are only applied when you click **Save** at the end — a green *"Successfully updated Job!"* confirms.
- **View Report:** shows the latest run's report — data appears only once the job has completed successfully at least once.

### 6.3 Restore

Route: `/backup-and-restore/restore`. The page opens on the **Restore** card (**"Create Restore Job"**) with the four connector tabs — **Exchange**, **Teams**, **SharePoint**, **OneDrive** — and, for non-trial users, the **Advanced Setup** toggle. Below the wizard, existing restore jobs are listed per connector under **Overview Restore Jobs**.

> **Important — restore jobs start disabled.** Every restore job is created with its schedule set to **Disabled**. To actually run it, go to **Overview Restore Jobs**, find the job, and click the green **Start** arrow under **Actions** (then **Yes, confirm**). This is a deliberate safety step so a restore never runs before you're ready.

> **Trial licenses** allow at most **2 restore jobs per connector**.

All connectors start the same way — **Step 1, General:** enter a **Job Name**. As with backups, the General settings can't be changed after the job is created. Click **Next**.

#### 6.3.1 Restore Exchange (e-mail)

1. **Account Selection** — search for and pick the **user (mailbox)** whose backed-up data you want to restore. You can scroll the list or type the first letters of the first or last name.
2. **Restore Type** — choose one:
   - **Mailbox Restore** — restore whole folders. A folder browser appears with two sub-tabs, **Include** and **Exclude**, plus an **"entire mailbox structure"** toggle to take everything. Tick the folders to restore (Include) or the folders to leave out (Exclude).
   - **Single Item Restore** — first pick a time window under **"Choose a period of time"** (**From Date** / **To Date**), then select the individual items to restore from the list that appears.
   - **Calendar Events Restore** — pick a date range on the calendar; all calendar items in that range are restored.
   - **Restore to a different mailbox** (toggle) — by default items go back to the **original** mailbox. Turn this on to instead choose a **target mailbox** (**Select Mailbox**) to receive the restored data. This is a *re-injection* into a live mailbox.
3. Click **Create**. A green *"Successfully created new job!"* confirms, and the job appears (Disabled) under **Overview Restore Jobs** — start it with the green **Start** arrow.

> **Reconciliation note (Admin Guide, Feb 2025).** The official Admin Guide describes the Exchange restore as three types — **Full Restore (Re-Injection)**, **Filter Restore (Re-Injection)**, and **Full Restore (Download)** — and a **Destination** choice of **Live Mailbox** vs **Exchange Online Archive**. The current application has reorganized this into the **Mailbox / Single Item / Calendar** restore types plus the **Restore to a different mailbox** toggle described above. The intent is the same (restore everything, restore a filtered subset, or restore to a different target); only the wording and layout have changed.

#### 6.3.2 Restore Teams

1. **Restore Type** — choose **Entire Team** (restore a whole team) or **Individual Channel into existing Team** (restore one or more channels).
2. **Users** — select the user to restore for (type the first ~3 letters of the surname, or scroll). Click **Next**.
3. **Backup Structure** —
   - For **Entire Team**: the selected user's restorable teams are shown; picking a team automatically includes its channels. You must also nominate a **new Team Owner** in the user selection.
   - For **Individual Channel into existing Team**: the restorable channels are shown; select the ones to restore and nominate the **Team Owner**.
4. Click **Create**. The job is created (Disabled) — start it from **Overview Restore Jobs**.

> When a team is (re)created by a restore, it is created **new** (the application may append a timestamp to the team name), and restoring channels adds a fresh, empty **General** channel.

#### 6.3.3 Restore SharePoint

1. **Site Selection** — search for or scroll to the SharePoint **site** to restore (search is case-sensitive). Select it and click **Next**.
2. **Restore Selection** — choose where to put it:
   - **Restore to original location** — restores the site in place. Click **Create**.
   - **Restore to new Site** — you must then define the **new site name**, the **ending of the new Site Address**, and the **owner** of the new site. Click **Create**.
3. The job is created (Disabled) — start it from **Overview Restore Jobs**.

> Creating a brand-new SharePoint site can take **one to two hours** to appear in the Microsoft 365 admin center.

#### 6.3.4 Restore OneDrive

1. **Account Selection** — pick the **user** whose OneDrive you want to restore. Click **Next**.
2. **Folder Selection** — choose the destination:
   - **Restore to original location** — restores into the user's own OneDrive. Click **Create**.
   - **Restore to specific Folder** — first choose which folder(s) from the **OneDrive backup** to restore (a backup browser with **Include**/**Exclude** sub-tabs and an **"entire account structure"** toggle). Then, on the **Live OneDrive** side, pick an existing destination folder **or** create one with **New Folder** (enter a name → **OK**; it appears under Live OneDrive to select). Click **Create**.
   - **Restore to another user** — restore into a **different** user's live OneDrive: select the target user, then pick or create the destination folder as above.
3. The job is created (Disabled) — start it from **Overview Restore Jobs**. Use **Detailed Report** next to the action icons to review a restore's outcome.

#### 6.3.5 Advanced restore & scheduling

- The **Advanced Setup** toggle (top-right) exposes additional **Filters** for restores that support them (e.g. message components and date properties for Exchange), inserted before the final step — mirroring the backup wizard's advanced filters ([§6.2.5](#625-advanced-filters-advanced-setup)).
- Because restores are always created **Disabled**, there is no recurrence to set at creation time — you start the job manually afterwards (or edit it later to schedule it).
- **Four‑eyes:** if the two-person rule is on, creating a restore triggers the approval flow before the job is created — see [§10.2](#102-four-eyes-two-person-approval).

### 6.4 Job Monitor

Route: `/backup-and-restore/job-monitor`. Shows jobs **in real time as they run**. The columns shown vary by connector — a running OneDrive backup shows different columns than a running Exchange backup. Typical columns include **Status/State**, **Progress**, **Started/Finished**, **Successful Count**, **Error Count**, processed counts and sizes, and **Total Runtime (HH:mm)**.

While a job is running you can:
- **Stop** it — click the **Stop** action (stop icon).
- **View its report mid-run** — click the report action to see progress details before the job finishes.

Statuses you may see include `STARTING`, `RUNNING`, `STOPPING`, `READY`, `FINISHED`, `FINISHED_SUCCESSFUL`, `FINISHED_WARNING`, `FAILED`, `PENDING`, `ABORTED`, and `CONNECTION_ERROR`.

### 6.5 Reports (Reporting)

Route: `/backup-and-restore/reports`. Lists **all jobs that have already run**. You can:
- Adjust rows per page (**5, 25, 50, or 100**) and page through results with the arrow control.
- **Search by job name** using the search box.
- Open **Detailed Reports** to see the individual accounts within a job. A successful account shows status **Finished**; if you see another status, check whether the account succeeds on its next run and contact support if it keeps failing.
- **Export** the data with **Export (CSV)** or **Export (XLSX)**.

### 6.6 User Dashboard (License Management)

Route: `/backup-and-restore/users`. The **License Management** view — per-user backup coverage and how your backup licenses are being consumed across the tenant.

> **Reconciliation note (Admin Guide, Feb 2025).** The Admin Guide also documents a **Mailboxes** statistics page (Top-10 mailboxes by items/size, exportable per location, with a **Backup** location option). In the current application, backup mailbox statistics are surfaced through the **Dashboard** ([§6.1](#61-dashboard)) and this **User Dashboard**; a standalone "Mailboxes" page remains part of the Email Archive area (see [§8](#8-email-archive--teams-archive)).

### 6.7 Hidden Jobs *(admin only)*

Route: `/backup-and-restore/hidden-jobs`. System-internal jobs (versioning, error recovery). Visible only to Super/System Administrators; hidden entirely for everyone else.

---

## 7. Data Management (Compliance)

The Data Management module (labelled **Compliance** in some places) governs file and version state across SharePoint and OneDrive. **Requires** `datamgmt.read`; links are disabled if the license excludes Data Management, and the File Manager / Monitoring / Reporting links are also disabled for the **trial** role.

> This is a newer module of the current application and is not covered by the Feb 2025 Admin Guide.

### 7.1 Dashboard
Route `/compliance/dashboard`. Aggregate SharePoint/OneDrive statistics — number of sites, files, and storage consumed — so you can see the scope of what Data Management is governing.

### 7.2 File Manager
Route `/compliance`. Browse the SharePoint/OneDrive structure like a file explorer:
1. Navigate into sites/drives and folders using the tree/breadcrumbs.
2. Search for a specific file.
3. Select an item to view its **compliance / archiving state** (whether it's archived, versioned, or subject to a data-management rule).

### 7.3 Job Monitor
Route `/compliance/monitoring`. Track data-management job execution in progress, with per-job status and progress.

### 7.4 Reports
Route `/compliance/reporting`. Retention and compliance analytics across your data-management activity.

### 7.5 Deletion & elevated access
Data-management job types include standard jobs and **Deletion** jobs. Deletion jobs that bypass retention require elevated approval (*"Require Elevated Access"* / *"Approve Archive Bypass"*), and administrators can maintain a **Deletion Blocklist** of protected users (by UPN/email) that must never be deleted.

---

## 8. Email Archive & Teams Archive

Compliance **archiving** (Email and Teams), **Deletion Jobs**, and **Proxy Rights** are delivered through **`portal.netmail.cloud`**.

> **Where these features live.** In this newer portal, the **Archive** menu is present but, apart from the **Dashboard** (`/archive/dashboard`), its links are disabled — the Dashboard shows a notice directing you to `portal.netmail.cloud` for archive operations. The workflows below document those archive operations as they run on `portal.netmail.cloud` (this matches the official Admin Guide, which is written for that portal). Archive features require an email/archive license (`archive.read`).

Archiving differs from backup: a **backup** is a protective copy you can restore from, while **archiving** moves/retains email and Teams content in compliance storage under retention rules, and **deletion jobs** remove data to satisfy legal retention limits or data-subject (GDPR) requests.

### 8.1 Email Archive — Dashboard

Shows your Exchange archiving at a glance: number of Exchange and archived mailboxes, licenses in use, archived messages and attachments, **system status**, and **Active Search Sessions** (how many users are currently searching the archive via the Search app). Messages and attachments are also broken down by your organization's individually configured **locations** (names and count are defined per customer).

### 8.2 Email Archive — Mailboxes (statistics)

Opens your mailbox statistics: the **Top 10** mailboxes in your organization, exportable, with a selector for the different **locations** you've defined. For each it shows the number of message and attachment items and where a user has items.

### 8.3 Email Archive — Create an Archive Job

Open **Create Archive Jobs** and work through the steps. (As elsewhere, the **General** parameters can't be changed after creation.)

1. **General** — give the job a **Name**, choose the **Job Type**, and select the **location** for the archiving. Click **Next**.
2. **Account Selection** — pick a single user, several users, or one/more distribution groups to archive. Click **Next**.
3. **Filters** —
   - **Source** — default is the **Primary Mailbox**.
   - **Message components** — choose which parts to archive: **Mail**, **Appointments (Termine)**, **Tasks (Aufgaben)**, **Notes (Notizen)**. Default is **Mail** only.
   - **Date Properties** — restrict archiving to a time range.
   - **Folder scope** — archive the entire folder structure, only selected folders, or all folders except excluded ones. **Folder spelling/path must be exact** for the rule to apply correctly.
   Click **Next**.
4. **Schedule** — run at a specific date, on a recurring rhythm, or leave **Disabled** (created and saved but only runs when you start it manually or edit it later to schedule it). You can enter an **email address** to be notified when the job completes. Click **Create**.

A green notification confirms the job was created; it then appears in the **Overview**.

### 8.4 Deletion Jobs

Deletion jobs remove archived data — used to meet statutory deletion deadlines or GDPR erasure requests. Open **Create Deletion Jobs**:

1. **General** — enter a **Name** and choose the **Job Type**. Click **Next**. (General settings are fixed after creation.)
2. **Account Selection** — search and select the user(s) or distribution group(s) to delete data from. Click **Next**.
3. **Filters** —
   - **Source** — default **Primary Mailbox**.
   - **Message components** to delete: **Mail**, **Appointments**, **Tasks**, **Notes** (default: Mail only).
   - **Date Properties** — the time range for the deletion.
   - **Folder scope** — the whole structure, only selected folders, or all except excluded ones (exact folder spelling matters).
   Click **Next**.
4. **Schedule** — a specific date, a recurring rhythm, or **Disabled**. You can enter an email address to be notified once the deletion has first run. Click **Create**.

The job appears under **Overview Deletion Jobs**, where you can review and edit it.

> Deletion jobs are powerful and irreversible. Where the portal enforces the four‑eyes rule, sensitive/retention-bypassing deletions require a second approver, and administrators can maintain a **Deletion Blocklist** of protected users (by UPN/email) that must never be deleted.

### 8.5 Proxy Rights

You can grant one user access to **another user's archive** (a delegation / representation right) for compliance archiving. Many customers mirror their Exchange delegation into the archive; this can be set up via support. Proxy rights are only relevant when your staff access the archive through the **Search** app.

### 8.6 Teams Archive

Teams archiving preserves Teams content in compliance storage.

- **Dashboard** — shows your archived teams, archived channels, and archived Teams chats and files.
- **Jobs** — lists your Teams archive jobs (**Overview**) and lets you create new ones.
  - **Start** an existing Teams archiving: click the green **Start** arrow under the action buttons → **Yes, confirm**. A green notification says it will start shortly.
  - **Create a Teams archive job** (**Create Archive Job**):
    1. **General** — enter a job name. Click **Next**.
    2. **Account Selection** — select the account(s) or a distribution list. Click **Next**.
    3. **Filters** — choose **Archive posts from all Teams**, **only specific Teams**, or **exclude specific Teams**. Click **Next**.
    4. **Schedule** — set the recurrence or leave **Disabled** to schedule later; optionally enter a completion-notification email. Click **Create**.
    A green notification confirms it saved, and the job appears under **Job Overview**.
- **Job Monitor** — shows running Teams archivings; stop one with the red **Stop** action.
- **Reporting** — lists successfully completed Teams archivings.

---

## 9. Account settings

Route: `/account/settings`. Three tabs:

### 9.1 Language
Title **"Portal Language"**. Choose **German** or **English**. The change applies immediately and is remembered for next time.

### 9.2 Notifications
Subtitle: **"Choose what we send you and how often."** Configure email reports:
- **Daily Reports** — *"A daily snapshot of your job activity, delivered every morning."*
- **Periodic Reports** — *"A recurring digest sent on the schedule you choose."*
Set the recipient and recurrence, and toggle notifications on/off.

### 9.3 Security — change password
Under **"Change Password"**, enter:
- **Current password** (error if blank: *"Please enter your current password."*)
- **Password** (new) and **Confirm Password**

Password rules: **7–42 characters**, at least **one uppercase** letter, and at least **one special character**.
- Success: **"Your password has been changed successfully."**
- Failure: **"Failed to change the password. Check your current password and try again."**

### 9.4 Support & Help Center
- **Support** (`/account/support`) — support contact information, reachable several ways from within the portal so you can call or email directly:
  - **Support:** +49 6126 5019 599 · support@sitaas.de
  - **Sales / licensing:** +49 6126 5019 500 · sales@sitaas.de
  - **Hours:** general Mon–Fri 09:00–17:00; technical hotline Mon–Fri 07:30–18:00 (subject to your individual support agreement).
  - If you obtained the product through **netmail EMEA GmbH**, contact your personal netmail contact / netmail Support.
- **Help Center** — an external link to help documentation.
- **Imprint** (`/account/imprint`) — legal/company information (the Online Compliance Center is a product of sitaas GmbH, combining sitaas and netmail technologies).

---

## 10. Administration (Configuration)

Route: `/configuration`. The **Configuration** entry appears when you can reach at least one of its tabs (four‑eyes, audit logs, or the cross-tenant admin block). Tabs are permission-gated, so you only see the ones you're entitled to.

| Tab | Who sees it | Purpose |
|---|---|---|
| **4-Eyes** | Client-scoped admins (`four-eyes.read`, not Super/System Admin) | Enable/disable the two-person rule; pick approvers. |
| **Audit Logs** | `audit-logs.read` (tenant-scoped) | Review tenant activity. |
| **Users** | Client Administrator (`four-eyes.manage`, client-scoped) | Manage this client's users and role assignments. |
| **User Management** | Super/System Admin (`users.list`, cross-tenant) | Cross-tenant user administration. |
| **Clients** | Super/System Admin | Create/edit/delete clients. |
| **Announcements** | Super/System Admin | Broadcast "What's new" messages. |
| **Tenant** | Super/System Admin | Tenant administration. |

### 10.1 Users & User Management

- **Users** (Client Administrator, one client): create users and assign roles scoped to that client. Assignable roles exclude Super Administrator, System Administrator, and Client Administrator.
- **User Management** (Super/System Admin, all tenants): create users across tenants and assign **any** role.

**User creation form fields:** **First Name**, **Last Name**, **User Email**, **Username**, **Role** (dropdown), **Email language** (English/German).
Actions: add user, **resend activation**, edit, delete.
Success: **"User has been created successfully"** / *"User created — an activation link has been emailed to them."*

### 10.2 Four-Eyes (two-person approval)

The **4-Eyes** rule requires a second authorized person to approve sensitive actions — principally **restore job creation** (the `restore.create` chokepoint).

**Configuring the rule** (4-Eyes tab):
- The current state is **Enabled**, **Disabled**, or **Enabled (pending)**.
- Choose the eligible **approver** (an **Administrator** or a **Data owner**) and the **Email language**.
- **Disabling** the rule itself requires approval: a disable request is sent to the selected second person (*"Disable 4-Eyes request has been sent"*).

**The approval flow** (when the rule is on):
1. A user creates a restore (or other gated) job. Because four‑eyes is enabled, the request is routed for approval and the user sees *"4-Eyes approval is required to continue"* / *"The job creation request has been sent to the selected admin."*
2. The approver receives an email with a magic link.
3. **Approver, not logged in** — opens `/four-eyes/approve` and sees a request headed *"4-Eyes Request to create a {connector} Restore Job with the {item type} {item}. This request has been created by {name}."* They click **Accept** or **Decline**.
   - Accept: **"Request Accepted Successfully."**  Decline: **"Request Declined Successfully."**
4. **Requester resumes** — after approval, the original requester (while logged in) opens `/four-eyes/resume` to finish creating the job. If they aren't the original requester: *"You are not allowed to approve this request."* If the link was already used: *"This process has been already tried."*

### 10.3 Clients
Create and manage clients. Fields: **Client Name**, **Abbreviation**, **Address**. Success: *"The client has been successfully created."*

### 10.4 Announcements
Create a short **"What's New"** message shown to users on the Homepage until they read it or it expires. Manage existing announcements, edit content, set a title and expiry.

### 10.5 Audit Logs
A tenant-scoped, read-only trail of user activity (logins, job creation, role changes, four‑eyes events, etc.). Mutations made through the portal are recorded automatically (super-admin actions are excluded from auto-logging).

### 10.6 Tenant
Tenant administration for Super/System Administrators (tenant records and settings).

---

## 11. Partner Config & Azure Dashboard

Both are Super/System-Administrator-only tools and are **hidden entirely** for anyone else.

- **Partner Config** (`/partner-setup`) — partnership setup (Super Administrator).
- **Azure Dashboard** (`/azure-dashboard`) — Azure cost analysis for the platform.

---

## 12. Reference appendices

### 12.1 Route map

**Public (no sign-in):**
`/signin`, `/logout`, `/forgot-password`, `/reset-password`, `/activate`, `/qr-setup`, `/code-verification`, `/account/new`, `/four-eyes/approve`, and any unknown path → 404.

**Authenticated:**
`/` and `/dashboard` (Overview), `/reports`, `/documents`;
`/backup-and-restore/{dashboard, backup-jobs, restore, job-monitor, reports, users, hidden-jobs}`;
`/compliance`, `/compliance/{dashboard, monitoring, reporting}`;
`/archive/{dashboard, jobs, deletion-jobs, job-monitor, reports, settings, users}`;
`/configuration`; `/account/{settings, support, imprint}`;
`/partner-setup`, `/azure-dashboard`; `/four-eyes/resume`.

### 12.2 Licenses & modules

License type identifiers and what they unlock:

| License group | Includes (identifiers) | Unlocks |
|---|---|---|
| Backup & Restore | `suite`, `data-management`, `archive-backup`, `backup_restore`, `email` | Backup dashboard/jobs, job monitor, reports (email-only license limits to email backup + user dashboard). |
| Full Backup & Restore | `suite`, `data-management`, `archive-backup`, `backup_restore` | Full backup **and** restore surface. |
| Data Management | `suite`, `data-management` | Data Management module. |
| Email Archive | `suite`, `compliance`, `archive-backup`, `email`, `archive` | Email archiving, archive jobs/reports/monitoring. |
| Compliance Archive | `suite`, `compliance` | Compliance archive features. |

A link is greyed out only when your license is a **known** value that excludes the module. A missing/unknown license does **not** disable links (permission gating still applies).

### 12.3 Environments (for administrators/operators)

The app runs in one of several modes: production, staging, or a self-contained mock mode used for local demos and training. In mock mode the app serves seeded demo data with no connection to a live environment. Deployment configuration (service endpoints, API keys, and the data-grid license key) is managed by your operators and is not exposed to end users.

### 12.4 Glossary

- **Connector** — a Microsoft 365 data source: Exchange, Teams, SharePoint, or OneDrive.
- **Tenant / Worker** — the Microsoft 365 organization context you're operating in. If you have access to several, the header lets you switch.
- **Four‑eyes** — the two-person approval rule for sensitive actions.
- **AIP** — Microsoft Information Protection (sensitivity labels).
- **Point-in-time** — restoring data as it existed at a chosen snapshot date.
- **Re-injection** — restoring email/Teams content back into the live Microsoft 365 environment (as opposed to a download).
- **Archiving vs backup** — archiving retains content in compliance storage under retention rules; backup is a protective copy you restore from.

### 12.5 Reconciliation with the Admin Guide (Feb 2025)

This manual documents the **current application**. The official **Admin Guide OCC (Feb 2025)** documents the production portal at `portal.netmail.cloud`. Where they differ:

| Topic | Admin Guide (Feb 2025) | Current application | Notes |
|---|---|---|---|
| **Product name** | Online Compliance Center (formerly netmail cloud / Cloud Portal since 2019; rebranded 2025) | Same | Naming history unchanged. |
| **MFA method** | 6-digit code emailed at each login (expires 5 min) | Authenticator app (TOTP) + recovery codes | Both are per-login MFA; delivery changed. See [§2.4](#24-two-factor-authentication-2fa). |
| **Idle logout** | 5 minutes | Automatic logout after inactivity | See [§2.5](#25-session-timeout). |
| **Exchange restore types** | Full Restore (Re-Injection) / Filter Restore / Full Restore (Download); Destination = Live Mailbox vs Exchange Online Archive | Mailbox / Single Item / Calendar restore + "Restore to a different mailbox" toggle | Same capabilities, reorganized. See [§6.3.1](#631-restore-exchange-e-mail). |
| **Per-job completion email** | Entered on the job's Schedule step | Notifications configured centrally under **Account → Notifications** | Archive/Teams-archive jobs on `portal.netmail.cloud` still offer the per-job email. |
| **Email Archive / Teams Archive / Deletion Jobs / Proxy Rights** | Fully functional in the portal | Delivered via `portal.netmail.cloud`; disabled in the newer portal except the Archive Dashboard notice | See [§8](#8-email-archive--teams-archive). |
| **Backup mailbox statistics** | "Mailboxes" page (Top-10, export by location) | Surfaced via Backup **Dashboard** + **User Dashboard**; a Mailboxes page remains in Email Archive | See [§6.6](#66-user-dashboard-license-management). |
| **Data Management (Compliance)** | Not documented | Present ([§7](#7-data-management-compliance)) | Newer module. |
| **Four‑eyes, eDiscovery Search app, cross-tenant admin** | Not documented | Present ([§10](#10-administration-configuration), companion Search manual) | Newer capabilities. |

### 12.6 Contact & support

- **Support:** +49 6126 5019 599 · support@sitaas.de
- **Sales / licensing:** +49 6126 5019 500 · sales@sitaas.de
- **Hours:** general Mon–Fri 09:00–17:00; technical hotline Mon–Fri 07:30–18:00 (per your support agreement).
- **Production portal:** `https://portal.netmail.cloud`
- Purchased via **netmail EMEA GmbH**? Use your netmail contact / netmail Support.

---

## 13. Troubleshooting

- **A menu link is greyed out.** Your tenant's license doesn't include that module. Contact your administrator about licensing.
- **A whole section is missing from the sidebar.** You don't hold the permission that reveals it (or it's an admin-only tool hidden from your role). Ask an administrator to review your role/permissions.
- **You were suddenly returned to the sign-in page.** Your session expired (a 401). Sign in again; if it recurs, clear cookies for the site.
- **"4-Eyes approval is required to continue."** Your restore/job needs a second approver. The approver must accept the emailed request, then you resume the job from the link. See [§10.2](#102-four-eyes-two-person-approval).
- **2FA is locked** after too many wrong codes. Enter your **recovery code** to unlock — this resets your authenticator; you'll re-scan a new QR code.
- **Activation link invalid/expired.** Ask an administrator to resend your invitation.
- **Archive links don't work.** Email Archive, Teams Archive, Deletion Jobs, and Proxy Rights are delivered via `portal.netmail.cloud`. Use the Archive Dashboard notice to get there. See [§8](#8-email-archive--teams-archive).
