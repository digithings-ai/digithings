# Vendored: twelve-x FX alarm reader

`fx_alarm_watch.py` in this directory is a **verbatim, unmodified** copy of the
pinned blob from the twelve-x repository. It is vendored so the caller in this
repo (`scripts/fx_alarm_caller.py`) runs the *same* reader twelve-x reviewed,
rather than a re-implementation that could drift.

- origin repo: `digithings-ai/twelve-x`
- source path: `scripts/fx_alarm_watch.py`
- blob sha1: `0bbd3527e8359c2192f4cdc4837b38a202d132ae`
- size: 2133 bytes

The vendored file carries **no header and no local edits** — a header would
change the blob and break the pin. Provenance lives here instead, and
`scripts/fx_alarm_caller.py --check-vendor` asserts the blob hash offline.

## Regenerate

```sh
git -C /path/to/twelve-x cat-file blob 0bbd3527e8359c2192f4cdc4837b38a202d132ae \
  > scripts/vendor/twelve_x/fx_alarm_watch.py
python3 scripts/fx_alarm_caller.py --check-vendor
```

The blob hash is git's blob-object sha1
(`sha1(b"blob <len>\0" + bytes)`), not `shasum -a 1` over the plain bytes.
