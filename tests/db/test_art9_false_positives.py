"""Art. 9 false-positive battery: ordinary business text must produce zero refusals.

Leaf L13 of the Art. 9 ingestion filter (DIG-1086). Spec acceptance test 11 on
DIG-912: *"A corpus of ordinary business, financial and technical text produces
zero refusals. A filter that trips on normal content gets switched off, so this
matters more than detection recall."* Plan leaf L13 on DIG-959.

Leaf L1 (`digibase/art9.py`) screens field names by **lowercased substring**,
the technique `digibase.audit` already uses. That rule over-triggers by design,
and its own docstring hands the decision to this file:

    *"Leaf L13 owns the false-positive battery and settles which of those to
    narrow or accept; narrowing here would pre-empt it and silently change the
    contract."*

**This file is the whole deliverable and it is a test, not a matcher fix.** If it
finds a false positive the leaf stops: the fix belongs in L1's matcher and
changing the matching technique is a second plan with the CTO, not a quiet
adjustment made inside a test leaf. So there is no `xfail`, no `skip`, no
softened sample and no denylist entry here. The battery is red where the corpus
is honest, and `test_ordinary_business_corpus_produces_zero_refusals` fails with
the full census in its message so the write-up is mechanical rather than a
remembered impression.

What is pinned here:

1. **The headline** — the corpus refuses nothing. This is acceptance test 11.
2. **The corpus is not soft.** `test_the_named_substring_risk_keys_are_present`
   asserts the field names L1 and the plan name by name actually occur as keys in
   the corpus. A future edit that deletes them to make (1) pass fails here
   instead, so "we softened the samples" is a red test rather than a silent
   improvement.
3. **The battery can fail.** `test_a_genuine_art9_payload_is_still_refused` is
   the positive control: if the corpus were somehow empty, or every assertion
   compared against a baseline that already refused, (1) could pass without the
   detector having been exercised at all.
4. **The allowed long forms stay allowed** — `healthcheck_url`, `trades`,
   `undiagnosed` — so a reader can see the rule is not simply "everything
   refuses".
5. **Prose that names a category without carrying its value is not detected**,
   which is §5.6's "no regex detects those in prose with usable precision" and
   is what keeps a battery of prose from being unfalsifiable.

Attribution in (1) uses the **public API only**: a key is blamed when
`screen_request({key: None})` refuses on its own, which isolates the field-name
rule from the identifier patterns. Where no key is at fault the refusal came
from a value pattern, and `reason`'s signal names which one. `reason` reports the
first hit in `category_order` with `field_name` outranking a value pattern, so a
sample that trips both is attributed to its key — stated here because the census
is what the escalation quotes.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from digibase import art9

pytestmark = pytest.mark.unit

# ── the corpus ───────────────────────────────────────────────────────────────
#
# Six source classes the brief names: invoices, contracts, support tickets,
# dashboards, meeting notes, technical runbooks. Sixteen samples, written to look
# like payloads this platform actually handles rather than like samples chosen to
# pass. Several carry field names the matcher is known to over-trigger on, on
# purpose — those are the samples the battery exists to measure.

CORPUS: tuple[tuple[str, Any], ...] = (
    # ── invoices ───────────────────────────────────────────────────────────
    (
        "invoice: clinical-laboratory order",
        {
            "invoice_number": "INV-2026-0417",
            "issued": "2026-09-28",
            "currency": "EUR",
            "purchase_order": "PO-88421",
            "vendor": "NordLab Analytics BV",
            "payment_terms_days": 30,
            "grace_period_days": 10,
            "cost_center": "RND-114",
            "lines": [
                {
                    "line_number": 1,
                    "description": "Hereditary breast/ovarian panel (BRCA1/BRCA2)",
                    "medical_billing_code": "81201",
                    "quantity": 12,
                    "unit_price": "318.00",
                    "line_total": "3816.00",
                },
                {
                    "line_number": 2,
                    "description": "Sample courier, ambient temperature",
                    "medical_billing_code": "88261",
                    "quantity": 12,
                    "unit_price": "24.50",
                    "line_total": "294.00",
                },
            ],
            "total": "4110.00",
        },
    ),
    (
        "invoice: cloud services",
        {
            "invoice_number": "INV-2026-5521",
            "vendor": "Northwind Cloud",
            "billing_period": "2026-08",
            "healthcheck_url": "https://status.northwind.example/healthz",
            "line_items": [
                {
                    "sku": "NC-COMPUTE-8",
                    "description": "8 vCPU reserved instance",
                    "quantity": 12,
                    "unit_price": "204.00",
                },
                {
                    "sku": "NC-OBJ-500",
                    "description": "500 GB object storage",
                    "quantity": 1,
                    "unit_price": "12.90",
                },
            ],
            "subtotal": "2461.80",
            "vat_rate": "0.22",
            "total": "3003.40",
        },
    ),
    (
        "invoice: freight",
        {
            "invoice_number": "FR-2026-00881",
            "carrier": "Baltic Freight Co",
            "waybill": "BF-99120-XK",
            "incoterm": "DAP",
            "gross_weight_kg": 812,
            "declared_value": "18400.00",
            "hs_code": "8413.70",
            "freight_terms_days": 45,
            "grace_period_days": 14,
        },
    ),
    (
        "lab order: sequencing",
        {
            "order_number": "LAB-2026-0772",
            "vendor": "NordLab Analytics BV",
            "requested_by": "genomics-core",
            "sample_count": 48,
            "dna_sequence_length": 8400,
            "assay": "targeted-panel-v3",
            "read_depth": 350,
            "turnaround_days": 12,
            "cost_per_sample": "142.00",
            "status": "in_lab",
        },
    ),
    # ── contracts ──────────────────────────────────────────────────────────
    (
        "contract: master services agreement",
        {
            "contract_id": "CTR-2026-0091",
            "counterparty": "Helvetia Systems SA",
            "effective_date": "2026-10-01",
            "initial_term_months": 24,
            "termination_notice_days": 90,
            "auto_renewal": True,
            "governing_law": "Switzerland",
            "liability_cap_eur": "500000.00",
            "service_credits": {"uptime_below_99_5_percent": "10 percent per month"},
            "data_processing_addendum": "DPA-2026-0091-2",
            "signature_block": {"name": "A. Keller", "title": "CFO", "signed": "2026-09-30"},
        },
    ),
    (
        "contract: works-council annex",
        {
            "nda_id": "NDA-2026-0413",
            "parties": ["Datatap BV", "Ironvale GmbH"],
            "effective_date": "2026-09-19",
            "confidentiality_term_years": 3,
            "permitted_disclosure": "need-to-know employees only",
            "works_council_consultation_required": True,
            "return_or_destroy_days": 14,
            "trade_union_consultation_required": False,
        },
    ),
    # ── support tickets ────────────────────────────────────────────────────
    (
        "support ticket: invoice pdf",
        {
            "ticket_id": "SUP-88214",
            "channel": "in_app",
            "subject": "Invoice PDF is missing the tax breakdown",
            "body": (
                "Customer says the PDF shows one line total. Asked for the "
                "itemised invoice with the VAT rate per line."
            ),
            "priority": "normal",
            "sla_hours_remaining": 6,
            "assignee": "support.queue.b",
            "product_version": "4.11.2",
            "tags": ["billing", "pdf", "eu"],
        },
    ),
    (
        "support ticket: device unlock",
        {
            "ticket_id": "SUP-88907",
            "subject": "Fingerprint unlock stopped after the OS update",
            "body": (
                "User reports the handset asks for a PIN after every reboot since "
                "14.2. Camera and keyboard are unaffected."
            ),
            "device": "Pixel 8a",
            "os_version": "Android 15",
            "biometric_auth_enabled": True,
            "enrolled_fingers": 2,
            "last_successful_unlock": "2026-09-27T08:14:02Z",
            "escalated": False,
        },
    ),
    (
        "support ticket: recurring checkout decline",
        {
            "ticket_id": "SUP-89033",
            "subject": "Card declined twice on a repeat subscription",
            "body": (
                "Two declines on the same subscription renewal. Issuer response "
                "code 51. Customer has sufficient balance."
            ),
            "order_id": "ORD-4419022",
            "amount": "49.00",
            "currency": "EUR",
            "payment_method": "visa_4242",
            "retry_count": 2,
            "grace_period_applied": False,
        },
    ),
    # ── dashboards ─────────────────────────────────────────────────────────
    (
        "dashboard: payments reliability",
        {
            "dashboard": "payments-reliability",
            "generated_at": "2026-10-09T06:00:00Z",
            "panels": [
                {
                    "panel": "checkout-latency",
                    "trace_id": "6f2a1c9e77b34d2f",
                    "healthcheck_url": "https://payments.example/healthz",
                    "latency_p99_ms": 812,
                    "error_rate": "0.004",
                },
                {
                    "panel": "retry-backoff",
                    "grace_period_seconds": 300,
                    "max_attempts": 5,
                    "thresholds": {"warn": 900, "page": 1500},
                },
            ],
        },
    ),
    (
        "dashboard: country risk",
        {
            "dashboard": "country-risk",
            "generated_at": "2026-10-09T06:00:00Z",
            "widgets": [
                {
                    "widget": "open-alerts",
                    "political_alerts": 4,
                    "new_since": "2026-10-07",
                    "regions": ["SK", "HU", "PT"],
                },
                {
                    "widget": "vendor-due-diligence",
                    "pending_reviews": 11,
                    "sla_days": 5,
                },
            ],
        },
    ),
    (
        "dashboard: delivery fleet",
        {
            "dashboard": "delivery-fleet",
            "generated_at": "2026-10-09T06:00:00Z",
            "vehicles": [
                {
                    "vehicle_id": "VAN-114",
                    "driver_shift": "morning",
                    "odometer_km": 88120,
                    "engine_fault": None,
                },
                {
                    "vehicle_id": "VAN-207",
                    "driver_shift": "afternoon",
                    "odometer_km": 41009,
                    "engine_fault": "P0420",
                },
            ],
            "on_time_rate": "0.94",
            "fuel_price_eur_per_litre": "1.71",
        },
    ),
    # ── meeting notes (prose) ──────────────────────────────────────────────
    (
        "meeting notes: q3 ops review",
        (
            "Q3 ops review. Checkout latency fell 18% after the retry rewrite, and "
            "the grace period now applies only to idempotent retries. Invoice "
            "volume was 412k lines, three of which needed a VAT correction. "
            "Support median 6h. Next: capacity for the November peak, and a "
            "runbook for the fleet dashboard."
        ),
    ),
    (
        "meeting notes: vendor renewal",
        (
            "Vendor renewal. Northwind Cloud renewed for twelve months at a 9% "
            "discount. Legal flagged the liability cap: it is uncapped for "
            "data-protection breaches, which they accepted. Finance wants the SLA "
            "credits written into the order form. Action: procurement sends the "
            "paper order by Friday."
        ),
    ),
    # ── technical runbooks (prose) ─────────────────────────────────────────
    (
        "runbook: rolling a digibase deploy",
        (
            "Rolling a digibase deploy. 1. Confirm the healthcheck_url for the "
            "new revision returns 200 for five minutes before shifting traffic. "
            "2. Draining: wait for in-flight requests to finish; the grace "
            "period is 30 seconds. 3. If the error rate exceeds 1% for two "
            "minutes, roll back to the previous image. 4. Record the artifact "
            "fingerprint descriptor and the commit sha in the change log. "
            "5. Announce in #platform-ops."
        ),
    ),
    (
        "runbook: speech synthesis profile",
        (
            "Speech synthesis profile. Pick the voice template in Settings > "
            "Voice, then adjust the speed. Voice embeddings for the selected "
            "profile are cached locally; clear them with 'reset voice cache'. "
            "Latency target is 400ms to first sample. In the UI the phrase 'face "
            "template' means the avatar, not the synthesis voice."
        ),
    ),
)

#: Field names the brief and the plan name by name, plus the two ordinary
#: technical keys the matcher's substring rule catches by accident. Asserted to
#: be present in the corpus so the battery cannot be made green by deleting the
#: samples that offend.
REQUIRED_KEYS: tuple[str, ...] = (
    "healthcheck_url",
    "medical_billing_code",
    "dna_sequence_length",
    "political_alerts",
    "trace_id",
    "grace_period_days",
    "biometric_auth_enabled",
)


# ── screening and attribution ───────────────────────────────────────────────


def _screen(payload: Any) -> art9.ScreenResult:
    """Screen one corpus sample the way a caller would.

    A bare string goes through `screen_text`; anything else through
    `screen_request`, which is what an ingest seam hands the detector. Neither is
    the test's own opinion of what should match.
    """
    if isinstance(payload, str):
        return art9.screen_text(payload)
    return art9.screen_request(payload)


def _iter_keys(node: Any, seen: set[int] | None = None) -> list[str]:
    """Every mapping key reachable from ``node``, at any depth.

    The detector walks lists and nested mappings, so a key four levels down is
    as available to it as one at the top and has to be available here too, or a
    nested false positive goes unreported.
    """
    walked: set[int] = set() if seen is None else seen
    if not isinstance(node, dict) or id(node) in walked:
        return []
    walked.add(id(node))
    keys = list(node)
    for value in node.values():
        if isinstance(value, dict):
            keys.extend(_iter_keys(value, walked))
        elif isinstance(value, (list, tuple)):
            for item in value:
                if isinstance(item, dict):
                    keys.extend(_iter_keys(item, walked))
    return keys


@dataclasses.dataclass(frozen=True)
class Finding:
    """One refusal in the corpus, attributed to its causes.

    ``blames`` holds **every** field name that refuses on its own, which is not
    the one ``reason`` names: ``reason`` reports the first hit in `category_order`,
    so a sample carrying both `grace_period_days` and `medical_billing_code`
    reports the health reason while the racial one is equally real. An empty
    tuple is what a value-pattern hit looks like from outside the module, and then
    ``reason``'s signal names the pattern.

    ``reason`` is art9's own stable code, so the escalation quotes the detector
    rather than this file.
    """

    sample: str
    blames: tuple[str, ...]
    categories: tuple[str, ...]
    reason: str

    def describe(self) -> str:
        where = ", ".join(self.blames) if self.blames else "<value pattern>"
        return f"{self.sample}: {where} -> {self.reason} {list(self.categories)}"


def _census() -> list[Finding]:
    """Every refusal in the corpus, one entry per refusing sample."""
    findings: list[Finding] = []
    for label, payload in CORPUS:
        result = _screen(payload)
        if result.decision == "allow":
            continue
        blames = tuple(
            key
            for key in _iter_keys(payload)
            if art9.screen_request({key: None}).decision == "refuse"
        )
        findings.append(
            Finding(
                sample=label,
                blames=blames,
                categories=result.categories,
                reason=result.reason,
            )
        )
    return findings


def _report() -> str:
    """A rendered census, readable as the escalation write-up."""
    findings = _census()
    blamed = sorted({key for f in findings for key in f.blames})
    categories = sorted({c for f in findings for c in f.categories})
    lines = [
        "",
        f"{len(findings)} of {len(CORPUS)} ordinary-business samples were refused.",
        "",
        *(f.describe() for f in findings),
    ]
    lines += [
        "",
        f"distinct field names blamed ({len(blamed)}): {', '.join(blamed) or 'none'}",
        f"categories invented ({len(categories)}): {', '.join(categories) or 'none'}",
        f"samples that refused ({len(findings)}): "
        f"{', '.join(f.sample for f in findings) or 'none'}",
        "",
        "Per the leaf brief this is a STOP, not a fix: the matcher belongs to L1",
        "and changing the matching technique is a second plan with the CTO.",
    ]
    return "\n".join(lines)


# ── the battery ──────────────────────────────────────────────────────────────


def test_ordinary_business_corpus_produces_zero_refusals() -> None:
    """Spec acceptance test 11, and the reason this leaf exists.

    A filter that trips on normal content gets switched off, and a switched-off
    filter is worse than no filter because the risk assessment still claims it
    is there. Sixteen samples across invoices, contracts, support tickets,
    dashboards, meeting notes and runbooks must all return ``allow``.

    The failure message is the census, not a count: it names every refusing
    sample, the field name blamed and the category invented, so the escalation
    can quote it.
    """
    findings = _census()

    assert findings == [], _report()


def _iter_strings(node: Any) -> list[str]:
    """Every string value reachable from ``node``, at any depth.

    Mapping keys are excluded on purpose: `_scan` sends keys through the
    field-name table and values through the identifier patterns, and this helper
    exists to measure the second half on its own.
    """
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for value in node.values() for s in _iter_strings(value)]
    if isinstance(node, (list, tuple)):
        return [s for item in node for s in _iter_strings(item)]
    return []


def _value_pattern_hits() -> list[tuple[str, str]]:
    """`(sample, reason)` for every corpus *value* an identifier pattern catches.

    Measured separately from `_census` because `reason` ranks `field_name` above
    every value pattern, so a sample that trips both reports only the field name.
    Without this the invoice's `BRCA1/BRCA2` line item would be invisible in the
    headline's failure message — a third of the evidence hidden behind a
    documented precedence.
    """
    hits: list[tuple[str, str]] = []
    for label, payload in CORPUS:
        for text in _iter_strings(payload):
            result = art9.screen_text(text)
            if result.decision == "refuse":
                hits.append((label, result.reason))
    return hits


def test_corpus_values_trip_no_identifier_pattern() -> None:
    """The value-pattern half of the battery, measured on its own.

    Field names and identifier patterns are two different techniques with two
    different false-positive surfaces, and `_decide` ranks a field-name hit above
    a value-pattern hit — so one assertion over `reason` cannot see both. This
    one screens every string in the corpus on its own, which is what `screen_text`
    does for a real caller.

    The false positives it finds are ordinary text: the name of a test panel on a
    lab invoice, and two runbook sentences about voice and face templates — the
    vocabulary a speech product uses for its own UI. Same STOP as the headline:
    the pattern belongs to L1 and changing it is a second plan.
    """
    hits = _value_pattern_hits()

    assert hits == [], "\n".join(
        [
            "",
            f"{len(hits)} ordinary-business strings tripped an identifier pattern:",
            *(f"  {label}: {reason}" for label, reason in hits),
            "",
            "Per the leaf brief this is a STOP, not a fix: the pattern belongs to",
            "L1 and changing the matching technique is a second plan with the CTO.",
        ]
    )


def test_every_corpus_sample_is_screened_through_the_public_api() -> None:
    """Sixteen samples, each screened, and none of them empty.

    `test_ordinary_business_corpus_produces_zero_refusals` would pass on an empty
    corpus or on a corpus of `None`s, so the corpus is asserted to be populated
    and every sample is screened through the public API and required to return a
    real verdict. Whether any sample *refuses* is deliberately not asserted here:
    that is the headline's job, and pinning it would make the second plan's fix
    impossible to land.
    """
    assert len(CORPUS) >= 12, "the corpus was trimmed; acceptance test 11 wants breadth"
    for label, payload in CORPUS:
        assert payload not in (None, {}, "", []), f"{label} is an empty sample"
        assert _screen(payload).decision in ("allow", "refuse"), label


def test_the_named_substring_risk_keys_are_present() -> None:
    """The samples that offend are not removable without failing here.

    `healthcheck_url`, `medical_billing_code`, `dna_sequence_length` and
    `political_alerts` are named by the plan; `trace_id` and `grace_period_days`
    are ordinary platform keys the substring rule catches by accident. If a later
    edit deletes them to make the headline green, this fails and says why the
    battery would then be proving nothing.
    """
    keys = {key for _, payload in CORPUS for key in _iter_keys(payload)}

    missing = [key for key in REQUIRED_KEYS if key not in keys]
    assert missing == [], f"corpus no longer covers {missing}; the battery proves nothing"


def test_a_genuine_art9_payload_is_still_refused() -> None:
    """The positive control: the battery is not green because nothing trips.

    If the matcher were neutered — or the corpus silently emptied — the headline
    would pass. These two payloads carry a §5.5 field name and a §5.5 identifier
    value, and both must still refuse, so "zero refusals" can only mean the
    corpus is clean and not that the detector is off.
    """
    by_name = art9.screen_request({"diagnosis": "type 2 diabetes, since 2019"})
    by_value = art9.screen_request({"note": "NHS number 943 476 5919"})

    assert by_name.decision == "refuse", by_name.reason
    assert by_name.reason == "art9:health:field_name", by_name.reason
    assert by_value.decision == "refuse", by_value.reason
    assert by_value.categories == ("health",), by_value.categories


@pytest.mark.parametrize("key", ["healthcheck_url", "trades", "undiagnosed", "membership_tier"])
def test_keys_the_spec_does_not_name_stay_allowed(key: str) -> None:
    """One character away from a needle, and none of them a category.

    §5.5 lists `health_status`, not `health`; `trade_union`, not `trade`;
    `diagnosis`, not `diagnos`; `union_membership`, not `membership`. A battery
    in which every plausible key refuses proves nothing about the rule, so these
    pin the other direction — including `healthcheck_url`, which the plan names
    as the risk to be settled here and which the current rule already lets
    through.
    """
    result = art9.screen_request({key: "value"})

    assert result.categories == (), key
    assert result.decision == "allow", key


def test_prose_naming_a_category_without_carrying_its_value_is_not_detected() -> None:
    """A field name in prose is not a field name in a payload.

    §5.6 rules prose detection of beliefs, opinions, sex life and union
    membership out of v1, and the identifier patterns are anchored on their
    labels for the same reason. An HR form instruction naming the date-of-birth
    field, and a runbook sentence naming a diagnosis field, carry no values and
    must allow — otherwise the prose half of the corpus could only ever fail.
    """
    form_instruction = (
        "Onboarding: the agent must enter the date of birth and the diagnosis "
        "code exactly as printed on the identity document, then continue to the "
        "next screen."
    )
    ops_note = (
        "The medical billing code and the political alerts widget are both "
        "misnamed in the schema; rename them in the next migration."
    )

    for prose in (form_instruction, ops_note):
        result = art9.screen_text(prose)
        assert result.decision == "allow", result.reason
        assert result.categories == (), prose
