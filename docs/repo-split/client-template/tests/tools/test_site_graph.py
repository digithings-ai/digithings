"""The site graph is one `/path - description` line per page and stays small."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_site_graph_lines() -> None:
    for graph in (ROOT / "tools" / "site-graph").glob("*.md"):
        text = graph.read_text()
        assert len(text.encode()) <= 16 * 1024, graph
        paths = [ln for ln in text.splitlines() if ln.startswith("/")]
        assert paths and all(" - " in ln for ln in paths), graph
