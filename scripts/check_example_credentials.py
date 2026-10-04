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
CRED_VAR_PATTERNS = [
    r'API_KEY', r'SECRET', r'TOKEN', r'PASSWORD', r'PRIVATE_KEY',
    r'CLIENT_SECRET', r'ACCESS_TOKEN', r'REFRESH_TOKEN',
    r'WEBHOOK_SECRET', r'SIGNING_KEY',
]
CRED_VALUE_PATTERNS = [
    # Vendor prefixes only: high-signal, short, and a prefix alone is enough.
    # The generic character-class entries are gone - they whitelisted an
    # alphabet, so a credential holding any other character was reported clean.
    # `looks_cred_val` now scores the value's own distribution instead.
    # None of these may be end-anchored: a prefixed key is routinely followed by a
    # trailing `# comment`, and an `$` would let that comment hide the key.
    r'^sk-[A-Za-z0-9]{20,}',
    r'^ghp_', r'^gho_', r'^glpat-',
]
#: Bits per character at or above which a value counts as a credential. Set
#: below the weakest probe (3.565) on purpose: the floor also has to cover the
#: encodings the removed character-class patterns caught - measured over 10 000
#: 32-character hex secrets, 3.5 misses 19.3%, 3.2 misses 0.4%, 3.0 misses ~0%
#: (none in 10 000 random samples, but a skewed string can still fall below it).
#: Precision comes from the inline-comment exclusion below, not from this floor.
CRED_MIN_ENTROPY = 3.0

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
    if len(v) < 16:
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
