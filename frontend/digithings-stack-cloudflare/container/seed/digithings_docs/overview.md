# digithings documentation — seed overview

This note is a **minimal** digithings.ai/chat grounding seed for the Profile A
stack digisearch index `digithings_docs`.

## What is digisearch?

digisearch is the RAG service in digithings. It indexes documents into named
collections (Chroma) and answers retrieval queries used by digigraph tools.

## What is digivault?

digivault stores Obsidian-style markdown notes. digigraph exposes
`digivault_search_notes` for full-text search over vault paths.

## Chat tools

Website digichat (Profile A) always retrieves via digisearch and
digivault_search_notes before answering. Cite source paths from tool results.
