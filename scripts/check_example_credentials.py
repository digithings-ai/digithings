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
    r'^(replace|REPLACE|CHANGE_ME|TODO|FIXME|CHANGEME)',
    r'<.*>',
    r'your_',
    r'example_',
    r'test_',
    r'dummy_',
    r'placeholder',
    r'changeme',
    r'^$',
]
CRED_VAR_PATTERNS = [
    r'API_KEY', r'SECRET', r'TOKEN', r'PASSWORD', r'PRIVATE_KEY',
    r'CLIENT_SECRET', r'ACCESS_TOKEN', r'REFRESH_TOKEN',
    r'WEBHOOK_SECRET', r'SIGNING_KEY',
]
CRED_VALUE_PATTERNS = [
    r'^[A-Za-z0-9]{32,}$',
    r'^[A-Za-z0-9+/]{20,}={0,2}$',
    r'^sk-[A-Za-z0-9]{20,}$',
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
    if len(v) < 16:
        return False
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
