---
name: summarize-tickets-by-topic
description: Group the tickets you retrieved into topics and report one line per ticket with its id, a topic count, and nothing that retrieval did not return.
version: "1"
---

# Summarize tickets by topic

Use this when you have been asked what a set of tickets is about — "summarize the
open tickets", "what are these tickets about", "group these by theme".

## Order of work

1. **Retrieve first.** Every ticket you report must come from a result you
   observed this turn. Retrieve before you write a word.
2. **Propose the topics yourself** from what the retrieved titles and text
   actually say. There is no fixed topic list. Name a topic in the customer's
   own words where you can.
3. **One line per ticket, with its id.** The id is not decoration — it is how
   the reader checks your work.
4. **Order by size**, largest topic first. Say how many tickets are in each.

## Output shape

```
## <one line naming the scope and how many tickets>

### <Topic>
- <TICKET-ID> — <what that one ticket is about, in one clause>

### <Topic>
- <TICKET-ID> — <what that one ticket is about, in one clause>

<one sentence: what the largest group has in common, and what is left over>
```

## What never goes in

- **A ticket id you did not retrieve.** Not a plausible one, not a remembered
  one, not one that fills a gap in the numbering. If a line has no ticket
  behind it, the line does not exist.
- **A topic no ticket supports.** Do not open a section for a theme you
  expected to find. "Nothing in this set was about billing" is a finding.
- **Anything about the customer that retrieval did not return** — their size,
  their plan, their industry, their history, how they feel about it.
- **Anything about what we can or cannot do** for them. Whether a capability
  exists is decided by what you observe while working, never by what you
  remember. See `present-results`.
- **Internal machinery.** Never mention how you looked something up, what you
  asked, what came back empty, or what you were told to do. The reader asked a
  question, not for a transcript.

## If retrieval found nothing

Say so in one line and stop. Do not fall back to what you happen to know about
the customer or the product.
