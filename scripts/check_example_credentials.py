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
# Words that read as a placeholder for any variable name.
GENERIC_PLACEHOLDER_VALUES = (
    'local', 'dev', 'development', 'test', 'localhost', 'none',
)
# Digi product names (see AGENTS.md "Naming"). These used to sit in the
# blanket placeholder allowlist, which is how PASSWORD=digichat sailed
# past the guard: for a credential-shaped variable a product name is a
# weak real credential, not a placeholder, so it is never exempt.
PRODUCT_NAME_VALUES = (
    'digichat', 'digigraph', 'digiquant', 'digisearch', 'digikey',
    'digivault', 'digiclaw', 'digibase', 'digitrace', 'digillm',
    'digifetch', 'digiskills', 'digiweb', 'digivoice', 'digidev',
    'digismith', 'digithings',
)
CRED_VAR_PATTERNS = [
    r'API_KEY', r'SECRET', r'TOKEN', r'PASSWORD', r'PRIVATE_KEY',
    r'CLIENT_SECRET', r'ACCESS_TOKEN', r'REFRESH_TOKEN',
    r'WEBHOOK_SECRET', r'SIGNING_KEY',
]
CRED_VALUE_PATTERNS = [
    # Bare alphanumeric, 16+ chars — Alpha Vantage-style keys are
    # exactly 16, so the old 32-char floor let them through.
    r'^[A-Za-z0-9]{16,}$',
    # Base64-shaped secrets.
    r'^[A-Za-z0-9+/]{20,}={0,2}$',
    # Provider key prefixes.
    r'^sk-[A-Za-z0-9]{20,}$',
    # CoinGecko-style keys (CG- + 16 alphanumerics); the hyphen
    # escaped every other pattern.
    r'^CG-[A-Za-z0-9]{16,}$',
    r'^ghp_', r'^gho_', r'^glpat-',
]

def is_placeholder(v):
    v = v.strip().strip('"').strip("'")
    for p in PLACEHOLDER_PATTERNS:
        if re.search(p, v, re.I):
            return True
    if v.lower() in GENERIC_PLACEHOLDER_VALUES:
        return True
    return False

def looks_cred_var(var):
    for p in CRED_VAR_PATTERNS:
        if p in var.upper():
            return True
    return False

def looks_cred_val(var, v):
    v = v.strip().strip('"').strip("'")
    # A product name is a weak real credential for a credential-shaped
    # variable (PASSWORD=digichat), however short — report it before
    # the length floor below can exempt it.
    if v.lower() in PRODUCT_NAME_VALUES and looks_cred_var(var):
        return True
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
                var = var.strip()
                if looks_cred_var(var) and looks_cred_val(var, val):
                    issues.append(f"{name}:{var}")
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
