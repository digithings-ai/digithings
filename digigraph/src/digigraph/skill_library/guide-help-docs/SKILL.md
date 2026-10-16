---
name: guide-help-docs
description: Map of the OCC help manuals (which section lives where) and the workflow for answering a how-to from those docs.
version: "1"
---

# Guide help docs

Use this for a how-to, a setting, a screen, or a procedure. Load this map
before you search, so you know which manual and which section to aim at. Do
not rediscover the structure from scratch on every question.

## Where to look

Search the help docs with `digisearch_occ_help`. Aim the query at the section
this map names, in the reader's words. Past tickets are a different lookup
(`digisearch_zammad_tickets`); use them only when the question is about a
problem someone already reported, and then follow `find-precedent-tickets`.

Excerpts are not the whole page. Keep searching until the step that answers
is in what you have read. Cite a help article URL when you have an http(s)
link, otherwise the manual and section, such as (Portal manual, 6) or
(Search manual, 7.2).

## Map

Two manuals, plus a short shared note. The public help pages and PDFs follow
this split. E-learning videos are out of scope: say so if asked.

**Shared (both apps).** Sign-in is email or username, password, then
two-factor authentication. Two-factor is enrolled in the Cloud Portal; OCC
Search sends the reader there when it is missing. The same roles apply to
both apps: Super Administrator, System Administrator, Client Administrator,
Client Manager, Search Manager, Backup & Restore Manager, Archive Manager,
Data Management Manager, Client System Reviewer, Client Search Reviewer, and
Restore Approver. Four-eyes (two-person approval): the portal gates restore;
Search gates a case that includes a sensitive archive location.

**Cloud Portal manual** — day-to-day protection of Microsoft 365 data
(backup, restore, compliance, archive jobs, users and roles).

| Section | What lives there |
|---|---|
| 1 Introduction | What the portal is, and the older netmail cloud name |
| 2 Getting started | Sign-in, activating an account, reset password, two-factor, session timeout, first login |
| 3 Roles and permissions | Role catalogue and the permission strings the menus follow |
| 4 The application shell | Sidebar, navigation, what a missing section means |
| 5 Overview | The Online Compliance Center home |
| 6 Backup and Restore | Backup jobs and restore |
| 7 Data Management | Compliance jobs (sidebar label Data Management) |
| 8 Email Archive and Teams Archive | Archive jobs. Delivered through portal.netmail.cloud |
| 9 Account settings | Portal language (German or English) and the signed-in account |
| 10 Administration | Users, roles, organizations, clients, announcements, four-eyes, audit logs |
| 11 Partner Config and Azure Dashboard | Partner and Azure dashboard screens |
| 12 Reference appendices | Reconciliation with the Admin Guide (Feb 2025) |
| 13 Troubleshooting | Portal problems, including a missing sidebar section |

**OCC Search manual** — eDiscovery over the archive: cases, search, tagging,
export. Legal holds are described and are not available in the app.

| Section | What lives there |
|---|---|
| 1 Introduction | What OCC Search is |
| 2 Getting started | Sign-in, two-factor, first-time setup, session, no access |
| 3 Roles and permissions | The search-relevant roles |
| 4 The Cases Hub | The list of cases |
| 5 Creating and managing cases | Create, edit, delete, change status |
| 6 The case workspace | Search tab and Browse tab |
| 7 Searching | Quick search, advanced search, saved criteria, syntax |
| 8 Browsing the archive | Browse without a query |
| 9 Working with results | What you can do with a hit list |
| 10 Inspecting a message | Open one message |
| 11 Tagging | Tag definitions, apply and remove, filter by tag |
| 12 Legal holds | Intended behaviour, and that it is not available. Do not describe it as working |
| 13 Exporting | Start an export; track, download, delete |
| 14 The case detail drawer | The side panel for one case |
| 15 Administration | Four-eyes for sensitive cases, audit log, assignments |
| 16 Reference appendices | Routes, what can be searched, sorting, glossary, reconciliation with the User Guide (April 2025) |
| 17 Troubleshooting | Search problems, including being stuck on two-factor setup |

Deletion Jobs and Proxy Rights, like Email Archive and Teams Archive, are
delivered through portal.netmail.cloud rather than the portal screens above.

## Order of work

1. **Pick the manual and the section from the map** before you search.
2. **Search that section** with `digisearch_occ_help`, using the reader's
   words plus the section's subject.
3. **Read past the excerpt** when the question needs a procedure, a list, a
   table, or the words every, all, or which.
4. **Answer from what you read**, and cite the section or the http(s) URL.
5. **Say the docs do not cover it** when search returns nothing for that
   section. Do not fill the gap from memory. If the map says a feature is
   not available, say that, and do not invent a workaround that the docs do
   not describe.

## Language of shown terms

The chat language is the language the user writes in. When an answer shows a
term, status, title, or quote that is not already in the chat language, put
the chat-language wording first and the original in parentheses and quotes.
When the chat is English: in progress ("in Bearbeitung"). When the source
text is already in the chat language, do not add a translation.
