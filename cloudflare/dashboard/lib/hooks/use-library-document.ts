"use client";

import { useAsyncData } from "@/lib/hooks/use-async-data";
import { getLibraryDocumentById, type LibraryDocumentResult } from "@/lib/queries";
import type { Doc } from "@/lib/types";

const FAILED_DOC: LibraryDocumentResult = {
  id: "",
  date: "",
  document_key: "",
  view: "markdown",
  markdown: "_Failed to load document._",
  payload: null,
};

function failedDocFor(match: Doc): LibraryDocumentResult {
  return { ...FAILED_DOC, id: match.id, date: match.date, document_key: match.path };
}

/** Fetch library markdown for a selected research/portfolio doc (SIMP-028 / SIMP-029). */
export function useLibraryDocument(match: Doc | null) {
  const empty: LibraryDocumentResult | null = null;
  return useAsyncData(
    empty,
    async () => {
      if (!match) return null;
      try {
        return await getLibraryDocumentById(match.id);
      } catch {
        return failedDocFor(match);
      }
    },
    [match?.id]
  );
}
