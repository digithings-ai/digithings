"""DIG-179 scratch helper (untracked, deleted before commit).

Prints per-token METADATA for a file (never the token itself): position, length,
Shannon entropy, character-class profile, whether it is an email address. Used to
decide precisely which tokens in a chat transcript are credential material and
which are ordinary prose.
"""
import math
import re
import sys
from collections import Counter

PATH = sys.argv[1]

TRIM = ".,;:!?()[]{}" + chr(34) + chr(39) + "<>*|"


def entropy(text: str) -> float:
    counts = Counter(text)
    total = len(text)
    if not total:
        return 0.0
    return -sum((n / total) * math.log2(n / total) for n in counts.values())


def profile(token: str) -> str:
    kinds = ""
    if any(c.islower() for c in token):
        kinds += "l"
    if any(c.isupper() for c in token):
        kinds += "U"
    if any(c.isdigit() for c in token):
        kinds += "d"
    if any(not c.isalnum() for c in token):
        kinds += "s"
    return kinds


text = open(PATH, encoding="utf-8").read()
for lineno, line in enumerate(text.split("\n"), 1):
    print(f"line {lineno} len={len(line)}")
    for col, token in enumerate(re.split(r"\s+", line)):
        if not token:
            continue
        core = token.strip(TRIM)
        if not core:
            continue
        print(
            f"  tok{col:>2} len={len(core):>3} ent={entropy(core):.2f} "
            f"class={profile(core)} email={'@' in core} has_at={'@' in token} "
            f"sep={repr(token[:1] if token[0] != core else '')}"
        )
