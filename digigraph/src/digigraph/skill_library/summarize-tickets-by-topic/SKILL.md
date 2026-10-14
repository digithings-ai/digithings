---
name: summarize-tickets-by-topic
description: Group the tickets you retrieved into topics and report one line per ticket with its id, a topic count, and nothing that retrieval did not return.
version: "1"
---

# Summarize tickets by topic

Use this when you have been asked what a set of tickets is about — "summarize the
open tickets", "what are these tickets about", "group these by theme".

## What each lookup is for

Semantic search (`digisearch_zammad_tickets`) is for exploration: finding
themes and similar subjects. It does not count tickets and it is not a
complete set. Counts and precise metrics must come from the Zammad metadata
tools (`aggregate_tickets` for counts and rankings, `ticket_report` for a
status report, `list_tickets` for a paged live list). Never report a count
taken from semantic-search hits.

## Order of work

1. **Retrieve first.** Every ticket you report must come from a result you
   observed this turn. Retrieve before you write a word. Use semantic search
   to explore themes. Use the Zammad metadata tools when the question asks
   how many, a ranking, or a precise list.
2. **Propose the topics yourself** from what the retrieved titles and text
   actually say. There is no fixed topic list. Name a topic in the customer's
   own words where you can.
3. **One line per ticket, with its id.** The id is not decoration — it is how
   the reader checks your work.
4. **Order by size**, largest topic first. Say how many tickets are in each.
5. **Keep topics specific.** A topic groups tickets about the same problem or
   request, not the same product area. Do not merge unrelated tickets into one
   broad topic; put tickets that fit nowhere under a final `Other` topic.
6. **Count, then check the counts.** A topic's count is the number of ticket
   lines under it, nothing else. Every retrieved ticket appears on exactly one
   line. Before answering, add the topic counts: the sum must equal the number
   of tickets in the heading. If it does not, fix the lines, not the numbers.

## Output shape

```
## <one line naming the scope and how many tickets>

### <Topic> (<count>)
- <TICKET-ID> — <what that one ticket is about, in one clause>

### <Topic> (<count>)
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

## Language of shown terms

The chat language is the language the user writes in. When an answer shows a
term, status, title, or quote that is not already in the chat language, put
the chat-language wording first and the original in parentheses and quotes.
When the chat is English: in progress ("in Bearbeitung"). When the source
text is already in the chat language, do not add a translation.
