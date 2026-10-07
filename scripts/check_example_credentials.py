#!/usr/bin/env python3
"""
Check tracked .example and .template files for credential-shaped values
that are not obvious placeholders. Fails if found.
"""
import re
import subprocess
import sys
from collections import Counter
from math import log2
from pathlib import Path

PLACEHOLDER_PATTERNS = [
    # A placeholder marker counts only as the *first* token, and the separator that
    # follows it is tolerated (`_` or `-`), so `your_openai_key_here` and
    # `your-litellm-key-here` both stay placeholders. An unanchored match let a real
    # credential hide behind a placeholder word sitting in the middle of the value.
    r'^(?:replace|change_?me|todo|fixme|placeholder|your|example|test|dummy)(?:[^A-Za-z0-9]|$)',
    r'^<.*>$',
    r'^$',
]
#: Name-side patterns. This is a substring test (`p in var.upper()`), so an entry
#: claims every name containing it. Matching is only half the guard: a line is
#: reported when the name matches *and* the value survives `looks_cred_val`, so
#: widening this list costs nothing on a corpus whose credential-named lines are
#: empty, placeholder or a comment - which is the case for every entry below, and
#: measured rather than assumed by
#: `test_check_example_credentials_access_key_names.py`.
CRED_VAR_PATTERNS = [
    r'API_KEY', r'SECRET', r'TOKEN', r'PASSWORD', r'PRIVATE_KEY',
    r'CLIENT_SECRET',
    # `ACCESS_TOKEN` was in this list and `ACCESS_KEY` was not, which left an AWS
    # access key ID out of scope before its value was ever looked at: the
    # `^AKIA[A-Za-z0-9]{16,}` rule below would have reported the key, but the name
    # gate ran first and said no. The identical value under `AWS_ACCESS_TOKEN` was
    # reported, so the value was never the problem - only the name was. This is the
    # repo's own spelling too: the R2 workflows read `R2_ACCESS_KEY_ID` and
    # `CHECKPOINT_ARCHIVE_R2_ACCESS_KEY`. It newly matches `SSH_ACCESS_KEY_ID`,
    # which is acceptable for the reason in the comment above.
    r'ACCESS_KEY', r'ACCESS_TOKEN', r'REFRESH_TOKEN',
    r'WEBHOOK_SECRET', r'SIGNING_KEY',
]
CRED_VALUE_PATTERNS = [
    # Vendor prefixes only: high-signal, short, and a prefix alone is enough.
    # The generic character-class entries are gone - they whitelisted an
    # alphabet, so a credential holding any other character was reported clean.
    # `looks_cred_val` now scores the value's own distribution instead.
    # Two rules for this list. No entry may be end-anchored (`$` or `\Z`): a
    # prefixed key is routinely followed by a trailing `# comment`, and the
    # anchor lets that comment hide the key. And a body class must be the
    # alphabet the vendor really uses, because a value carrying a comment never
    # reaches the entropy score below - the prose exclusion runs first - so this
    # loop is the only gate that can catch it. This is a list of vendor
    # prefixes, not a shape rule: a prefix the guard has never heard of reports
    # clean behind a comment while the identical key is reported bare, which is
    # the false negative this list exists to close.
    #
    # `sk-` bodies are base64, and both alphabets occur in the wild. URL-safe
    # base64 (`-` and `_`) covers the two common families (`sk-proj-`,
    # `sk-ant-api03-`) that put a `-` inside the first 20 characters; standard
    # base64 puts `+` and `/` there instead. A body class that omits either of
    # those stops at the first character it does not hold, which is how a key
    # hides behind the comment that follows it. Base64's `=` padding is
    # deliberately left out: it only ever occurs at the tail of a body, so it
    # cannot be the character that satisfies the `{20,}` count below, and
    # admitting it would only let a too-short body match on its padding. Match
    # the value, not the line: a greedy class over a whole line is what put the
    # generic patterns back.
    r'^sk-[A-Za-z0-9_+/-]{20,}',
    r'^ghp_', r'^gho_', r'^glpat-',
    # Stripe. `sk_live_` is 8 characters, and the rest of a real key is a
    # 24-character body, so a floor of 20 sits under the real length rather
    # than at a copied constant.
    r'^sk_live_[A-Za-z0-9]{20,}',
    # Google. `AIza` is 4, and the documented key is 35 characters of
    # URL-safe base64 after it - a floor of 20 stays under that, since the
    # prefix alone is already a high-signal token.
    r'^AIza[A-Za-z0-9_-]{20,}',
    # AWS. An access key ID is 20 characters *in total*, so the body is 16 and
    # a 20-character floor would miss every real key. The class is wider than
    # the alphabet AWS issues, which is upper-case only: it is permissive on
    # purpose because the prefix alone carries the signal and the class only
    # bounds the length. The committed `aws_akia` probe is what pins this - its
    # body is lower-case, so an upper-case-only class would fail the probe and
    # no prose in the tracked example files begins with `AKIA`.
    r'^AKIA[A-Za-z0-9]{16,}',
    # AWS temporary (STS) access key IDs, `ASIA`, are the same 20 characters in
    # total and are issued in real deployments, so they take the same floor.
    # Leaving this prefix out reported a temporary credential clean behind a
    # comment while the identical bare key was reported, which is the exact
    # false negative this list exists to close.
    r'^ASIA[A-Za-z0-9]{16,}',
    # HuggingFace. `hf_` is 3, then an opaque 34-character token.
    r'^hf_[A-Za-z0-9]{20,}',
    # Slack. A bot token is three hyphen-separated groups after the prefix, so
    # the class has to hold `-`; a 20-character floor clears the 10-13 digit
    # first group and its separator and still stops short of the whole token.
    r'^xoxb-[A-Za-z0-9-]{20,}',
    # SendGrid. The `.` is a literal in the key, hence the escape. A key is a
    # fixed 69 characters - `SG.`, a 22-character id, a separator, then a
    # 43-character secret - so the first run of the body is well past this
    # floor. The class only has to cover that first run, because nothing here
    # is end-anchored and the separator is not part of the alphabet being
    # matched.
    r'^SG\.[A-Za-z0-9_-]{20,}',
]
#: Bits per character at or above which a value counts as a credential. Set
#: below the weakest probe (3.565) on purpose: the floor also has to cover the
#: encodings the removed character-class patterns caught - over 100 000 random
#: 32-character hex secrets, 3.5 misses 18.8%, 3.2 misses 0.36%, 3.0 misses
#: 0.006% (6 in 100 000; the observed minimum was 2.936). Precision comes from
#: the inline-comment exclusion below, not from this floor.
CRED_MIN_ENTROPY = 3.0
#: Shortest value the guard will score at all. The name has already matched
#: `CRED_VAR_PATTERNS` by this point, so length is all that separates a real key
#: from the short human words a developer writes under a credential name.
#: Nothing in the tracked corpus sets the bound - every credential-named line
#: there is empty, a placeholder, or a `#` comment - so the shortest pinned
#: probe sets it, at 12.
CRED_MIN_VALUE_LEN = 12
#: Length at or above which `CRED_MIN_ENTROPY` is a meaningful test. That floor is
#: bits *per character*, so below the length it was calibrated at the rate reports
#: sample size rather than randomness: over 40 000 random hex secrets per length a
#: 3.0 bits/char floor misses 45.7% at 12 characters and 14.0% at 16, against the
#: 0.006% at 32. 17 is the narrowest band any pinned probe needs - the 16-character
#: one scores 2.750, exactly level with `postgres`, so no threshold separates the
#: two - the other three score 3.022, 3.155 and 3.301 and clear the floor unaided.
CRED_MIN_ENTROPY_LEN = 17

def is_placeholder(v):
    v = v.strip().strip('"').strip("'")
    for p in PLACEHOLDER_PATTERNS:
        if re.search(p, v, re.I):
            return True
    low = v.lower()
    if low in ('digichat', 'local', 'dev', 'development', 'test', 'localhost', 'none'):
        return True
    return False

def looks_cred_var(var):
    for p in CRED_VAR_PATTERNS:
        if p in var.upper():
            return True
    return False

def shannon_entropy(v: str) -> float:
    """Shannon entropy of ``v`` in bits per character; 0.0 for an empty string."""
    if not v:
        return 0.0
    n = len(v)
    # `+ 0.0` normalizes the `-0.0` a single-symbol string would otherwise return.
    return -sum((c / n) * log2(c / n) for c in Counter(v).values()) + 0.0

def looks_cred_val(v):
    v = v.strip().strip('"').strip("'")
    if len(v) < CRED_MIN_VALUE_LEN:
        return False
    if is_placeholder(v):
        return False
    for p in CRED_VALUE_PATTERNS:
        if re.match(p, v):
            return True
    # Prose is rejected before any score is taken. The lowest probe scores
    # 3.565 and the live inline comments in `.env.example` score 4.005 and
    # 4.348, so no threshold separates the two groups: whitespace, or a leading
    # `#`, is what marks a value as a comment rather than a token. That costs a
    # passphrase written with real internal spaces, accepted on purpose.
    if v.startswith('#') or any(c.isspace() for c in v):
        return False
    # Below `CRED_MIN_ENTROPY_LEN` the rate cannot set the floor, but it can still
    # refute a value: one repeated symbol scores 0.0 bits, which is evidence
    # against a credential rather than an absence of evidence for one.
    if len(v) < CRED_MIN_ENTROPY_LEN:
        return shannon_entropy(v) > 0.0
    return shannon_entropy(v) >= CRED_MIN_ENTROPY

def main():
    try:
        result = subprocess.run(['git', 'ls-files'], stdout=subprocess.PIPE, text=True, check=True)
        tracked = [Path(f) for f in result.stdout.splitlines()]
    except Exception:
        tracked = list(Path('.').rglob('*'))
    issues = []
    for f in tracked:
        name = str(f)
        if not ('.example' in name or '.template' in name):
            continue
        try:
            for line in f.read_text(errors='replace').splitlines():
                s = line.strip()
                if not s or s.startswith('#') or '=' not in s:
                    continue
                var, val = s.split('=', 1)
                if looks_cred_var(var.strip()) and looks_cred_val(val):
                    issues.append(f"{name}:{var.strip()}")
        except Exception:
            continue
    if issues:
        print('ERROR: non-placeholder credential values found', file=sys.stderr)
        for i in issues:
            print(f'  {i}', file=sys.stderr)
        return 1
    print('OK')
    return 0

if __name__ == '__main__':
    sys.exit(main())
