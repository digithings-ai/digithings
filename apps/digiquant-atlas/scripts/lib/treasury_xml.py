"""US Treasury daily yield curve XML (public, no API key)."""

from __future__ import annotations

from xml.etree import ElementTree

TREASURY_XML_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/"
    "interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value={yyyymm}"
)

# XML property suffix -> short label (matches fetch-macro.py)
TREASURY_MATURITIES = [
    ("1_MONTH", "1M"),
    ("2_MONTH", "2M"),
    ("3_MONTH", "3M"),
    ("6_MONTH", "6M"),
    ("1_YEAR", "1Y"),
    ("2_YEAR", "2Y"),
    ("3_YEAR", "3Y"),
    ("5_YEAR", "5Y"),
    ("7_YEAR", "7Y"),
    ("10_YEAR", "10Y"),
    ("20_YEAR", "20Y"),
    ("30_YEAR", "30Y"),
]

DS = "http://schemas.microsoft.com/ado/2007/08/dataservices"
DSM = "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"


def _get_prop(props, name: str) -> str | None:
    el = props.find(f"{{{DS}}}{name}")
    return el.text if el is not None else None


def parse_treasury_month_xml(xml_text: str) -> list[tuple[str, dict[str, float]]]:
    """
    Parse all curve dates in one Treasury monthly XML response.
    Returns list of (curve_date YYYY-MM-DD, yields dict label -> percent).
    """
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []

    entries = root.findall(".//{http://www.w3.org/2005/Atom}entry")

    out: list[tuple[str, dict[str, float]]] = []
    for entry in entries:
        props = entry.find(f".//{{{DSM}}}properties")
        if props is None:
            continue
        raw_date = _get_prop(props, "NEW_DATE") or ""
        curve_date = raw_date[:10] if len(raw_date) >= 10 else ""
        if not curve_date:
            continue
        yields: dict[str, float] = {}
        for xml_key, label in TREASURY_MATURITIES:
            val = _get_prop(props, f"BC_{xml_key}")
            if val:
                try:
                    yields[label] = round(float(val), 4)
                except ValueError:
                    pass
        if yields:
            out.append((curve_date, yields))
    return out
