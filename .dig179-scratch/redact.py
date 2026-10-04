"""DIG-179 scratch helper (untracked, deleted before commit).

Redacts a chat-transcript file so its structure can be inspected without any
secret value entering the model's context. Prints a masked view only.
"""
import math
import re
import sys
from collections import Counter

PATH = sys.argv[1]

KEYWORD = re.compile(
    r"(?i)(passw|passcode|pwd|secret|login|credenziale|chiave|token|otp|2fa)"
)
TRIM = ".,;:!?()[]{}" + chr(34) + chr(39) + "<>*|"


def entropy(text: str) -> float:
    counts = Counter(text)
    total = len(text)
    if not total:
        return 0.0
    return -sum((n / total) * math.log2(n / total) for n in counts.values())


def is_boring(core: str) -> bool:
    return bool(re.fullmatch(r"[\d:.\-\[\]/ ]+", core))


def masked_view(text: str) -> str:
    rendered = []
    for line in text.split("\n"):
        pieces = []
        after_keyword = False
        for token in re.split(r"(\s+)", line):
            core = token.strip(TRIM)
            if not core:
                pieces.append(token)
                continue
            if after_keyword:
                pieces.append(token.replace(core, "<<R-AFTER-KEYWORD>>"))
                continue
            risky = (
                "@" not in core
                and len(core) >= 6
                and not is_boring(core)
                and entropy(core) >= 3.0
            )
            if risky:
                pieces.append(token.replace(core, "<<R-ENTROPY>>"))
                continue
            pieces.append(token)
            if KEYWORD.search(core):
                after_keyword = True
        rendered.append("".join(pieces))
    return "\n".join(rendered)


if __name__ == "__main__":
    print(masked_view(open(PATH, encoding="utf-8").read()))
