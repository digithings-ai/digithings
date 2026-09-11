"""20-query web-search eval cases (#3853, task 9).

Offline-first: the harness in ``test_web_search_eval.py`` mocks the search
provider and the digifetch fetcher, so every case runs with no network and no
searxng sidecar. ``must_contain`` substrings are matched case-insensitively
against the enriched markdown snippet; the mocked fixture page embeds each
query verbatim, so distinctive query keywords are the right assertions.

Live mode (opt-in): ``DIGISEARCH_WEB_SEARCH_LIVE=1`` runs one sampled case
per category against the real backends and asserts p50 fetch+extract < 5s.
"""

CASES = [
    # news — market-moving headlines
    {
        "query": "bitcoin etf daily flows record",
        "category": "news",
        "must_contain": ["bitcoin", "etf"],
    },
    {
        "query": "nvidia earnings data center revenue beat",
        "category": "news",
        "must_contain": ["nvidia", "data center"],
    },
    {
        "query": "opec production quotas oil price outlook",
        "category": "news",
        "must_contain": ["opec", "oil"],
    },
    {
        "query": "tesla quarterly deliveries production total",
        "category": "news",
        "must_contain": ["tesla", "deliveries"],
    },
    {
        "query": "sp 500 closing breadth advance decline",
        "category": "news",
        "must_contain": ["breadth", "decline"],
    },
    # macro — policy and data releases
    {
        "query": "federal reserve rate decision dot plot",
        "category": "macro",
        "must_contain": ["federal reserve", "dot plot"],
    },
    {
        "query": "cpi inflation shelter housing costs",
        "category": "macro",
        "must_contain": ["cpi", "shelter"],
    },
    {
        "query": "ecb deposit facility rate cut guidance",
        "category": "macro",
        "must_contain": ["ecb", "deposit facility"],
    },
    {
        "query": "nonfarm payrolls unemployment rate revision",
        "category": "macro",
        "must_contain": ["payrolls", "unemployment"],
    },
    {
        "query": "bank of japan rate hike yen intervention",
        "category": "macro",
        "must_contain": ["japan", "yen"],
    },
    # docs — stack and product knowledge
    {
        "query": "digisearch chroma backend persistent client setup",
        "category": "docs",
        "must_contain": ["digisearch", "chroma"],
    },
    {
        "query": "digigraph orchestration hub vertical tools",
        "category": "docs",
        "must_contain": ["digigraph", "orchestration"],
    },
    {
        "query": "digichat embed tenant gate turn limited",
        "category": "docs",
        "must_contain": ["digichat", "turn limited"],
    },
    {
        "query": "digikey jwt scopes digisearch query auth",
        "category": "docs",
        "must_contain": ["digikey", "scopes"],
    },
    {
        "query": "litellm proxy redis cache shared deployment",
        "category": "docs",
        "must_contain": ["litellm", "redis"],
    },
    # earnings — company results
    {
        "query": "apple iphone revenue services margin quarter",
        "category": "earnings",
        "must_contain": ["apple", "iphone"],
    },
    {
        "query": "microsoft azure cloud growth guidance",
        "category": "earnings",
        "must_contain": ["microsoft", "azure"],
    },
    {
        "query": "jpmorgan net interest income outlook",
        "category": "earnings",
        "must_contain": ["jpmorgan", "interest income"],
    },
    {
        "query": "asml euv bookings lithography demand",
        "category": "earnings",
        "must_contain": ["asml", "euv"],
    },
    {
        "query": "nestle organic growth pricing power",
        "category": "earnings",
        "must_contain": ["nestle", "organic growth"],
    },
]


def fixture_html(query: str, keywords: list[str]) -> str:
    """Deterministic article html embedding the query plus a table and a list.

    The offline harness serves this from the mocked digifetch fetcher so the
    service enrichment path runs with no network and no searxng sidecar.
    """
    keys = " ".join(keywords)
    return (
        "<html><body><article>"
        f"<h1>{query}</h1>"
        f"<p>{query} update ({keys}): desks cite steady breadth while "
        "analysts watch follow-through into the next session.</p>"
        "<table><tr><th>metric</th><th>reading</th></tr>"
        f"<tr><td>{keywords[0] if keywords else 'breadth'}</td><td>firm</td></tr>"
        "</table>"
        "<ul>"
        f"<li>{query} breadth widened</li>"
        f"<li>{keys} held into the close</li>"
        "</ul>"
        "</article></body></html>"
    )
