# Online Compliance Center — User Manuals

This folder contains the end-user and administrator manuals for the two applications that make up the **Online Compliance Center (OCC)** platform.

| Manual | Application | What it covers |
|---|---|---|
| **[portal-manual.md](./portal-manual.md)** | **Cloud Portal** (`cloud-portal-ui`) | Microsoft 365 backup & restore, data management/compliance, email archive, reporting & documents, and administration (users, roles, tenants, clients, announcements, four‑eyes, audit logs). |
| **[search-manual.md](./search-manual.md)** | **OCC Search** (`occ-search`) | The eDiscovery workspace: cases, searching & browsing the archive, message preview, tagging, and exporting. |

Each manual is a **full reference** written for both everyday users and administrators, using the exact wording that appears in the applications.

> **Keeping these docs in sync with the code:** see **[MAINTENANCE.md](./MAINTENANCE.md)** — it maps every manual section to its source-of-truth files in each repo and gives a repeatable re-sync procedure and verification checklist.

---

## The two applications at a glance

- **Cloud Portal** is where you protect and govern your Microsoft 365 data day to day — scheduling backups, running restores, managing compliance, and administering users and tenants.
- **OCC Search** is where legal/compliance reviewers investigate archived mailbox data — organizing work into cases, searching, tagging, and exporting. (Legal holds are defined in the permission model but **not available** in the app — see [search-manual §12](./search-manual.md#12-legal-holds).)

They are separate web apps but one platform: the portal even has an **eDiscovery** menu entry that points at the Search app (disabled inside the portal itself).

---

## Shared identity, roles & permissions

Both apps authenticate against the same identity service and use one common model. Understanding it once applies to both manuals.

### Sign-in & MFA
- Both apps use email/username + password, followed by **two-factor authentication (2FA/MFA)** via an authenticator app, with recovery codes as a backup.
- **MFA is enrolled in the Cloud Portal.** If OCC Search finds your account hasn't set up MFA, it sends you to the portal to enroll, then back.

### Roles
The built-in roles are shared across the platform:

| Role | Scope | Notes |
|---|---|---|
| **Super Administrator** | All tenants | Every permission. |
| **System Administrator** | All tenants | Every permission. |
| **Client Administrator** | One client/tenant | Manages users; controls the four‑eyes rule. One per client. |
| **Client Manager** | One tenant | All four domain managers + portal read + user/role admin. |
| **Search Manager** | One tenant | Full search/eDiscovery domain. |
| **Backup & Restore Manager** | One tenant | Backup & restore jobs. |
| **Archive Manager** | One tenant | Archive jobs & locations. |
| **Data Management Manager** | One tenant | Data-management jobs. |
| **Client System Reviewer** | One tenant | Read-only portal/system. |
| **Client Search Reviewer** | One tenant | Read-only search. |
| **Restore Approver** *(capability)* | — | Held alongside a primary role for four‑eyes approvals. |

**Assignment rules:** Super/System Administrators can assign any role (including Client Administrator and other admins). A Client Administrator can assign any role except the two cross-tenant admins and Client Administrator itself (separation of duties).

### Permissions
Every capability is a fine-grained permission string (e.g. `backup.create`, `restore.create`, `cases.read`, `search.execute`, `tags.manage`, `exports.create`, `audit-logs.read`). The UI shows or hides menus, tabs, and buttons based on the permissions your account holds. In the portal, module links are additionally **disabled** when your tenant's **license** doesn't include that module.

The full permission catalogue is listed in [portal-manual.md §3.2](./portal-manual.md#32-permissions-catalogue); the search-relevant subset is in [search-manual.md §3](./search-manual.md#3-roles--permissions-reference).

### Four-eyes (two-person approval)
Both apps implement a **four‑eyes** rule for sensitive actions:
- **Portal:** gates sensitive job creation (principally **restore**). See [portal-manual §10.2](./portal-manual.md#102-four-eyes-two-person-approval).
- **Search:** gates creating/editing a case that includes a **sensitive archive location**. See [search-manual §15.1](./search-manual.md#151-four-eyes-approval-for-sensitive-cases).

In both cases the flow is the same shape: a requester triggers the action → an approver receives an email with a magic link → the approver **approves/denies** → the requester **resumes** to complete the action.

---

## Notes on accuracy

- These manuals were written from the application source: route definitions, UI locale/label files, role and permission definitions, and feature components. Quoted labels are taken verbatim from the apps.
- They are **reconciled with the official product documentation** — the **Admin Guide OCC (Feb 2025)** for the portal and the **User Guide – Search (April 2025)** for search. Where the current apps differ from those guides (for example MFA method, or features delivered via `portal.netmail.cloud`), each manual includes *Reconciliation notes* and a summary table (portal §12.5, search §16.6).
- Where a feature is **disabled, unreleased, or has moved**, the manuals say so up front rather than describing it as working. Most notably: **Email Archive, Teams Archive, Deletion Jobs, and Proxy Rights** are delivered through `portal.netmail.cloud`; and **legal holds in OCC Search are not available** despite having permissions defined for them ([search-manual §12](./search-manual.md#12-legal-holds)).
- Both apps can run against a built-in **mock/demo mode**; in that mode the data is seeded sample data rather than your live tenant.
- The manuals describe what the apps do for end users and administrators; they do not name internal back-end services.
