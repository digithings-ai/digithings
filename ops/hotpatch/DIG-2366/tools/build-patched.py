#!/usr/bin/env python3
"""DIG-2366: build the patched bundle files from the pinned 2026.1001.0 baseline.

Reads ops/hotpatch/DIG-2366/baseline/** (byte-for-byte copies of the live
bundle files as found) and writes ops/hotpatch/DIG-2366/patched/**.

Never touches the live bundle. Fails loudly if an anchor line is not exactly
where it is expected, so a drifted baseline can never be half-patched.
"""
import hashlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASELINE = ROOT / "baseline"
PATCHED = ROOT / "patched"


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def edit_in_place(path: pathlib.Path, edits: list[tuple[int, int, str]], label: str) -> None:
    """edits: list of (start_line, end_line, replacement) 1-indexed inclusive."""
    lines = path.read_text().splitlines(keepends=True)
    for start, end, replacement in sorted(edits, key=lambda e: -e[0]):
        lines[start - 1 : end] = [replacement]
    path.write_text("".join(lines))
    print(f"  patched {label}: {len(edits)} edits")


def expect(path: pathlib.Path, lineno: int, text: str) -> None:
    lines = path.read_text().splitlines()
    actual = lines[lineno - 1]
    if actual != text:
        raise SystemExit(
            f"ANCHOR DRIFT in {path.name} line {lineno}\n"
            f"  expected: {text!r}\n"
            f"  actual:   {actual!r}"
        )


# ---------------------------------------------------------------- documents.js
def build_documents() -> None:
    src = BASELINE / "services" / "documents.js"
    dst = PATCHED / "services" / "documents.js"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())

    # Anchor checks against the pinned baseline before touching anything.
    expect(src, 4, 'import { isSystemIssueDocumentKey, issueDocumentKeySchema } from "@paperclipai/shared";')
    expect(src, 124, "            const key = normalizeDocumentKey(rawKey);")
    expect(src, 134, "            const key = normalizeDocumentKey(rawKey);")
    expect(src, 158, "            const key = normalizeDocumentKey(input.key);")
    expect(src, 512, "            const key = normalizeDocumentKey(input.key);")
    expect(src, 601, "            const key = normalizeDocumentKey(input.key);")
    expect(src, 644, "            const key = normalizeDocumentKey(rawKey);")
    expect(src, 687, "            const key = normalizeDocumentKey(rawKey);")

    helper = '''/**
 * Fault 1 (DIG-2365). `issueDocumentKeySchema` is /^[a-z0-9][a-z0-9_-]*$/, so a
 * lowercase uuid is a valid document key. Every lookup below filtered on
 * `issueDocuments.key` alone, which can never match `documents.id`, so a write
 * addressed by document id found no row, minted a second document keyed by the
 * uuid and answered 201. Resolve a uuid-shaped key against `documents.id`
 * first; report an unresolvable one as "no document" so each caller keeps the
 * not-found semantics it already has instead of minting a shadow row.
 */
async function resolveIssueDocumentKey(exec, issueId, rawKey) {
    const key = normalizeDocumentKey(rawKey);
    if (!isUuidLike(key))
        return key;
    const byDocumentId = await exec
        .select({ key: issueDocuments.key })
        .from(issueDocuments)
        .innerJoin(documents, eq(issueDocuments.documentId, documents.id))
        .where(and(eq(issueDocuments.issueId, issueId), eq(documents.id, key)))
        .then((rows) => rows[0] ?? null);
    return byDocumentId ? byDocumentId.key : null;
}
'''

    edits: list[tuple[int, int, str]] = [
        # import the existing uuid helper the routes already use
        (
            4,
            4,
            'import { isSystemIssueDocumentKey, isUuidLike, issueDocumentKeySchema } from "@paperclipai/shared";\n',
        ),
        # helper, inserted after normalizeDocumentKey (closes on line 15)
        (15, 15, "}\n" + helper),
        # getIssueDocumentByKey -> null, as an unknown key already returns null
        (
            124,
            124,
            "            const key = await resolveIssueDocumentKey(db, issueId, rawKey);\n"
            "            if (key === null)\n"
            "                return null;\n",
        ),
        # listIssueDocumentRevisions -> empty list, as an unknown key already yields none
        (
            134,
            134,
            "            const key = await resolveIssueDocumentKey(db, issueId, rawKey);\n"
            "            if (key === null)\n"
            "                return [];\n",
        ),
        # upsertIssueDocument -> 409, this is the write that used to answer 201
        (
            158,
            158,
            "            const key = await resolveIssueDocumentKey(db, input.issueId, input.key);\n"
            "            if (key === null) {\n"
            "                throw conflict(\"Document key is a document id that does not belong to this issue\", {\n"
            "                    key: normalizeDocumentKey(input.key),\n"
            "                    issueId: input.issueId,\n"
            "                    resolvedBy: \"documents.id\",\n"
            "                });\n"
            "            }\n",
        ),
        # restoreIssueDocumentRevision / lockIssueDocument / unlockIssueDocument
        # already throw notFound("Document not found") below for a missing row.
        (
            512,
            512,
            "            const key = await resolveIssueDocumentKey(db, input.issueId, input.key);\n"
            "            if (key === null)\n"
            "                throw notFound(\"Document not found\");\n",
        ),
        (
            601,
            601,
            "            const key = await resolveIssueDocumentKey(db, input.issueId, input.key);\n"
            "            if (key === null)\n"
            "                throw notFound(\"Document not found\");\n",
        ),
        (
            644,
            644,
            "            const key = await resolveIssueDocumentKey(db, issueId, rawKey);\n"
            "            if (key === null)\n"
            "                throw notFound(\"Document not found\");\n",
        ),
        # deleteIssueDocument -> null, as an unknown key already returns null
        (
            687,
            687,
            "            const key = await resolveIssueDocumentKey(db, issueId, rawKey);\n"
            "            if (key === null)\n"
            "                return null;\n",
        ),
    ]
    edit_in_place(dst, edits, "services/documents.js")


# ------------------------------------------------------------------- issues.js
def build_issues() -> None:
    src = BASELINE / "routes" / "issues.js"
    dst = PATCHED / "routes" / "issues.js"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())

    expect(src, 8981, '    router.patch("/issues/:id", validateIssueMutationBody(updateIssueRouteSchema), async (req, res) => {')
    expect(
        src,
        9014,
        "        const { comment: commentBody, commentClientRequestId, attachmentIds: commentAttachmentIds, reviewInteractionId: requestedReviewInteractionId, reviewRequest, reopen: reopenRequested, resume: resumeRequested, interrupt: interruptRequested, deferWakeForGoal, hiddenAt: hiddenAtRaw, onBehalfOfUserId: _requestedOnBehalfOfUserId, ...updateFields } = req.body;",
    )

    guard = '''        // Fault 2 (DIG-2365). updateIssueSchema advertises reviewInteractionId, but
        // assertInReviewReviewPath returns null unless the same PATCH also sets
        // status: in_review, and nothing else reads the field. Outside a transition
        // it was dropped behind a 200 with an empty changes map. Refuse it instead
        // of losing it; it stays accepted during the transition.
        if (requestedReviewInteractionId !== undefined &&
            updateFields.status !== "in_review") {
            res.status(422).json({
                error: "reviewInteractionId requires status: in_review in the same request",
                details: {
                    code: "review_interaction_requires_in_review",
                    reviewInteractionId: requestedReviewInteractionId,
                    acceptedInteractionKinds: ["request_confirmation", "request_checkbox_confirmation"],
                },
            });
            return;
        }
'''
    edit_in_place(dst, [(9014, 9014, (dst.read_text().splitlines(keepends=True)[9013]) + guard)], "routes/issues.js")


def main() -> None:
    print("building patched files from the pinned 2026.1001.0 baseline")
    build_documents()
    build_issues()
    print("\n=== sha256 ===")
    for rel in ("services/documents.js", "routes/issues.js"):
        base = BASELINE / rel
        pat = PATCHED / rel
        print(f"{sha256(base)}  baseline/{rel}")
        print(f"{sha256(pat)}  patched/{rel}")
        if sha256(base) == sha256(pat):
            raise SystemExit(f"FAIL: {rel} unchanged")
    print("\nOK: both files differ from baseline as expected")


if __name__ == "__main__":
    main()