---
name: find-precedent-tickets
description: Find earlier tickets that already resolved the problem in front of you, rank them by how close they are, and cite the ids — or say none was found.
version: "1"
---

# Find precedent tickets

Use this when a new ticket needs an answer you may already have given: "has
this happened before", "did we already solve this", "what did we do last time
this came up".

## Where to look

Search past tickets with semantic search (`digisearch_zammad_tickets`). Use it
to find similar cases and how they were resolved. It is not a count and it is
not the live list. Read the closest matches before you advise a fix, and cite
the ticket numbers that search returned. For the status, the articles, or the
owner of one of those tickets, use the Zammad metadata tools (`get_ticket`,
and `search_tickets` when you already have a number or a field filter).

## Order of work

1. **Restate the symptom in the customer's words** before you search. Their
   phrasing finds earlier tickets; our category names do not.
2. **Search on the symptom, not the diagnosis.** You do not yet know the cause,
   so a search on the cause quietly drops the hits.
3. **Read what comes back before ranking it.** A title match is not a precedent.
   Read how the ticket was resolved, not only its title.
4. **Rank by closeness**, and say what made each one a match: same symptom,
  same root cause, or only the same product area.
5. **Advise the fix first**, then the evidence. Lead with what was done last
  time and cite the precedent tickets; the tickets are how the reader checks it.

## Output shape

```
**Answer:** <what was done last time, or: no earlier ticket covers this>

| Ticket | How close | What it settled |
|---|---|---|
| <TICKET-ID> | same symptom, same cause | <one line> |
| <TICKET-ID> | same symptom, different cause | <one line> |

<one line: why you are confident, or what would raise confidence>
```

## What never goes in

- **A ticket id retrieval did not return.** An invented id is worse than no
  answer: it is checkable, and it will fail the check.
- **A match you did not read.** If you have not seen the text, it is not a
  precedent, however well the title fits.
- **"There is no precedent" when you did not search.** No result is only ever
  "nothing matched this search". Say the search, then the emptiness.
- **A customer fact retrieval did not return**, and **anything about what we
  can or cannot do** — see `present-results`.

## When the closest match is only partly close

Give it, and label it as partly close. Dropping a partial match because it is
not exact loses the one thing the reader was looking for.

## Language of shown terms

The chat language is the language the user writes in. When an answer shows a
term, status, title, or quote that is not already in the chat language, put
the chat-language wording first and the original in parentheses and quotes.
When the chat is English: in progress ("in Bearbeitung"). When the source
text is already in the chat language, do not add a translation.
