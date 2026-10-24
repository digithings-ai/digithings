#!/usr/bin/env python3
"""
Check tracked .example and .template files for credential-shaped values
that are not obvious placeholders. Fails if found.
"""
import re
import subprocess
import sys
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
# Once CRED_VAR_PATTERNS has matched the variable name, length is not evidence of
# anything: a `*_API_KEY` holding a short opaque value is exactly what this guard
# exists to catch, so length may only be used to clear the short human words that
# are legitimately not credentials. The longest of those is `postgres` at 8, and
# 12 is the floor window's upper bound -- see DIG-43.
MIN_CRED_VALUE_LEN = 12

CRED_VALUE_PATTERNS = [
    r'^[A-Za-z0-9]{%d,}$' % MIN_CRED_VALUE_LEN,
    r'^[A-Za-z0-9+/]{%d,}={0,2}$' % MIN_CRED_VALUE_LEN,
    # the prefix counts toward the floor, so the value as a whole is at least this long
    r'^sk-[A-Za-z0-9]{%d,}$' % (MIN_CRED_VALUE_LEN - 3),
    r'^ghp_', r'^gho_', r'^glpat-',
]

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

def looks_cred_val(v):
    v = v.strip().strip('"').strip("'")
    if len(v) < MIN_CRED_VALUE_LEN:
        return False
    # the anchored placeholder gate has to run before any value shape, because
    # `your-api-key` scores higher on entropy than a real short key does
    if is_placeholder(v):
        return False
    for p in CRED_VALUE_PATTERNS:
        if re.match(p, v):
            return True
    if re.match(r'^[A-Za-z0-9_\-.]{32,}$', v):
        return True
    return False

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
