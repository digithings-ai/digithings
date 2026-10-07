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

#: Values that point at a credential instead of being one, told apart by shape
#: alone. Without these, a length floor reports every opaque example value in the
#: tree: under a credential name a value only has to be long and varied to be
#: scored at all, and "long and varied" is what an example password is.
#:
#: `looks_cred_val` applies this list *after* the vendor prefix loop, so a
#: vendor-prefixed key is reported whatever shape it wears - the ordering is the
#: recall argument, not an accident. And `is_non_secret_shape` refuses any value
#: containing whitespace before it looks at a single pattern, so a value
#: carrying an inline `# comment` - the shape the prefix loop exists to catch,
#: and the one DIG-749 makes reportable - can never be excluded here.
NON_SECRET_VALUE_SHAPES = [
    # A reference the shell, an orchestrator or a template engine resolves at
    # deploy time (`${VAR}`, `${VAR:-}`, `$(VAR)`, `{{ var }}`, `<% var %>`,
    # `$VAR`). The secret lives in whatever this resolves against; the file
    # carries its name. A *non-empty* default (`${API_KEY:-s3cret}`) is
    # deliberately not matched: a literal written under a credential name is
    # what this guard exists to report, wherever it happens to sit. The operator
    # list is spelled out so only the ones whose expansion may be empty are
    # accepted; `${API_KEY:-=}` is not a thing any of them emits.
    r'\$\{[A-Za-z_][A-Za-z0-9_]*(?:[:?][-+=+]?|[-=+]|\?)?\}',
    r'\$\(\s*[A-Za-z_][A-Za-z0-9_]*\s*\)',
    r'\{\{\s*[A-Za-z_][A-Za-z0-9_.]*\s*\}\}',
    r'<%\s*[A-Za-z_][A-Za-z0-9_.]*\s*%>',
    r'\$[A-Za-z_][A-Za-z0-9_]*',
    # A delimiter fence - PEM headers, `***` banners - the same character at both
    # ends around an interior that holds no delimiter at all. Framing, not
    # payload: `-----BEGIN-----` is a promise that a key follows, not a key. A
    # real encoding cannot be framed this way, because three identical
    # delimiters in a row is not something base64, base64url or hex emits at a
    # token boundary. Two details keep the match cheap as well as sure. The
    # interior excludes the delimiter, so there is only one way to match and no
    # backtracking to speak of; and the whole value is bounded to 80 characters,
    # because a fence longer than that is data wearing fence characters. Neither
    # detail is decoration: unbounded, this pattern costs 4x per doubling on a
    # long run of delimiters, and `is_non_secret_shape` runs on every line of
    # every example file in the tree.
    r'(?=.{3,80}$)([-=_.+*#:~@/])\1{2,}[^=_.+*#:~@/-]*\1\1{2,}',
    # A placeholder marker followed by numeric filler - `changeme1234`,
    # `placeholder123`. `PLACEHOLDER_PATTERNS` already names both markers as
    # leading tokens, but its separator class `[^A-Za-z0-9]` rejects the digit run
    # that follows, so the marker is dropped and 3.4 bits of digit entropy carry
    # the value over the floor alone. Restating the marker list here rather than
    # widening that separator keeps `PLACEHOLDER_PATTERNS` untouched and this
    # class revertible on its own. The digit run is unbounded on purpose: capping
    # it would put a cliff at the cap where `test12345678` reads as a placeholder
    # and `test123456789` reads as a credential.
    r'(?:replace|change_?me|todo|fixme|placeholder|your|example|test|dummy)[-_.]?\d+',
]
#: A connection template: a URI, or userinfo in front of a host. It says where to
#: connect, not how to authenticate, and in a file meant to be committed the
#: password in it is a variable. The `@` has to follow the `:`, so a password
#: that merely contains an `@` (`P@ss:word`) is not a locator.
_LOCATOR_SCHEME_RE = re.compile(r'[A-Za-z][A-Za-z0-9+.\-]*(?::[A-Za-z0-9+.\-]+)?://')
_LOCATOR_USERINFO_RE = re.compile(r'[^\s:/@]+:[^\s:/@]*@[^\s:/@]+')
_LOCATOR_SEPARATOR_RE = re.compile(r'[/\\?&#=;:@,;%+]+')


def is_connection_template(v):
    """True when ``v`` is a locator that carries no credential of its own.

    Being a URI is not on its own enough. A locator has one place a secret can
    hide in each of its parts - userinfo, a `key=` query parameter, a webhook
    token in the path - and every one of them is long enough for this guard to
    have something to say about it. So the locator is a template only when no
    part of it is: when nothing it points at is as long as a value this guard
    scores on its own, `user:pass@host` and
    `jdbc:postgresql://u:p@localhost:5432/app` are connection templates, while
    `redis://u:Sup3rS3cretPw2026@cache:6379/0` and a completions endpoint whose
    `key=` parameter holds a vendor-prefixed token are leaks. The line is this
    guard's own value floor, which is the honest place to draw it: an embedded
    secret shorter than 12 characters would not have been reported on its own
    either.

    The errors run one way on purpose. A locator with no `://` and no userinfo is
    not a locator and is scored like any other value; a locator carrying a long
    part is reported as a leak. The class can only ever be wrong about a value
    it declines to report, and it is built to decline as few as it can.
    """
    if not (_LOCATOR_SCHEME_RE.match(v) or _LOCATOR_USERINFO_RE.match(v)):
        return False
    return all(len(part) < CRED_MIN_VALUE_LEN for part in _LOCATOR_SEPARATOR_RE.split(v))


def is_non_secret_shape(v):
    """True when ``v`` is a reference to a credential rather than one.

    Refuses whitespace up front, so no value with a trailing `# comment` can be
    excluded by any shape here, and matches every pattern in full, so nothing
    can ride along behind a shape either.
    """
    if any(c.isspace() for c in v):
        return False
    if is_connection_template(v):
        return True
    return any(re.fullmatch(p, v, re.I) for p in NON_SECRET_VALUE_SHAPES)


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
    # Shape exclusions come after the prefix loop on purpose: a vendor prefix is
    # the strongest signal this guard has, so no shape may outrank it. It does
    # not need to. A prefixed key is 24 characters of base64 by the time it is
    # worth reporting, and the shapes below are all things a prefixed key is not
    # - a template reference, a locator, a delimiter fence, a placeholder word
    # followed by digits.
    if is_non_secret_shape(v):
        return False
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
