"""The committed release trust anchor must be a public key, not empty.

F1 (R-Q2) bounds the software key with `valid-before="20261201Z"`. git 2.50
compares that bound against the *tagger time of the tag being verified*, so a
tag cut before 2026-12-01T00:00Z keeps verifying while a later tag is refused.
That is what lets `r0-v0.1.1` and `strategies-v0.1.0` stay valid until every
consumer pins a tag signed by the current agent key (K2).

`test_existing_tags_still_verify` is the one network-dependent test here: it
fetches the real tag objects (trees excluded) and verifies them against this
committed file. It skips when the network is unavailable, which is why it is
marked `integration` and not `unit`.
"""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SIGNERS = ROOT / "scripts" / "deploy" / "allowed_signers"

# The reviewed bounds: K1 keeps the old line; K2 adds the rotating key.
VALID_BEFORE = "20261201Z"
NEW_VALID_BEFORE = "20270601Z"
PROMOTION_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINKq/T6JvmayBhm/nZZyYZnz7SZc+Ef+h/+vCoN1vrvl"

# Key types that may stand between the options field and the base64 key.
# `sk-` prefixed types remain accepted by the parser for compatibility, but
# the permanent policy is software Ed25519 (D-S1).
KEY_TYPES = (
    "sk-ssh-ed25519@openssh.com",
    "sk-ecdsa-sha2-nistp256@openssh.com",
    "ssh-ed25519",
    "ssh-rsa",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
)

# Real release tags, checked against the committed file. Both were cut with the
# software key while its tagger time was inside the bound.
RELEASE_TAGS = (
    ("https://github.com/digithings-ai/digithings.git", "r0-v0.1.1"),
    ("https://github.com/digithings-ai/digiquant-strategies.git", "strategies-v0.1.0"),
)


def _key_lines() -> list[str]:
    return [
        line.strip()
        for line in SIGNERS.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _split(line: str) -> tuple[str, dict[str, str], str, str]:
    """Split an allowed-signers line into principal, options, key type and key."""
    fields = line.split()
    key_index = next((index for index, field in enumerate(fields) if field in KEY_TYPES), None)
    assert key_index is not None, f"no key type in allowed-signers line: {line!r}"
    options: dict[str, str] = {}
    for raw in " ".join(fields[1:key_index]).split(","):
        if not raw:
            continue
        name, _, value = raw.partition("=")
        options[name] = value.strip('"')
    return fields[0], options, fields[key_index], fields[key_index + 1]


def _is_hardware(line: str) -> bool:
    return _split(line)[2].startswith("sk-")


def _as_date(value: str) -> str:
    """Normalise an allowed-signers date (YYYYMMDD or YYYYMMDDZ) to YYYYMMDD."""
    digits = value[:-1] if value.endswith("Z") else value
    assert len(digits) == 8 and digits.isdigit(), f"not a UTC date: {value!r}"
    return digits


def _run(
    cwd: Path,
    *args: str,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
        check=False,
    )


@pytest.fixture()
def signed_tag_setup(tmp_path: Path) -> tuple[Path, Path]:
    """A tmp repo and signers file using a throwaway ed25519 key and the reviewed bound."""
    if shutil.which("ssh-keygen") is None:  # pragma: no cover - macOS/Linux always have it
        pytest.skip("ssh-keygen is not installed")

    key = tmp_path / "release_key"
    keygen = _run(
        tmp_path,
        "ssh-keygen",
        "-t",
        "ed25519",
        "-f",
        str(key),
        "-N",
        "",
        "-C",
        "release@digithings",
        "-q",
    )
    assert keygen.returncode == 0, keygen.stderr

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "f").write_text("signed tag fixture\n")
    for step in (
        ("git", "init", "-q"),
        ("git", "config", "user.email", "release@digithings"),
        ("git", "config", "user.name", "release"),
        ("git", "config", "gpg.format", "ssh"),
        ("git", "config", "user.signingkey", str(key)),
        ("git", "add", "f"),
        ("git", "commit", "-q", "-m", "signed tag fixture"),
    ):
        result = _run(repo, *step)
        assert result.returncode == 0, result.stderr

    signers = tmp_path / "allowed_signers"
    signers.write_text(
        f'release@digithings namespaces="git",valid-before="{VALID_BEFORE}" '
        f"{key.with_suffix('.pub').read_text().strip()}\n"
    )
    return repo, signers


def _sign_tag(repo: Path, name: str, tagger_date: str) -> subprocess.CompletedProcess[str]:
    return _run(
        repo,
        "git",
        "tag",
        "-s",
        name,
        "-m",
        name,
        env=os.environ | {"GIT_COMMITTER_DATE": tagger_date},
    )


def _verify(repo: Path, signers: Path, tag: str) -> subprocess.CompletedProcess[str]:
    return _run(
        repo,
        "git",
        "-c",
        f"gpg.ssh.allowedSignersFile={signers}",
        "verify-tag",
        tag,
    )


@pytest.mark.unit
def test_allowed_signers_has_a_release_key() -> None:
    lines = _key_lines()
    assert len(lines) == 2, f"expected K1 and K2 release keys, found {len(lines)}"
    for line in lines:
        principal, options, key_type, _ = _split(line)
        assert principal == "release@digithings", "unexpected release principal"
        assert options.get("namespaces") == "git", "release key is not restricted to git"
        assert key_type == "ssh-ed25519", "release key is not software ed25519"


@pytest.mark.unit
def test_release_key_is_software_ed25519_and_unexpired() -> None:
    lines = _key_lines()
    bounds = []
    for line in lines:
        _, options, key_type, _ = _split(line)
        assert key_type == "ssh-ed25519", "unexpected key type; D-S1 requires software ssh-ed25519"
        assert "valid-before" in options, f"key without valid-before: {line!r}"
        bounds.append(_as_date(options["valid-before"]))
    assert max(bounds) == _as_date(NEW_VALID_BEFORE)
    assert datetime.strptime(max(bounds), "%Y%m%d").replace(tzinfo=UTC) > datetime.now(UTC)


@pytest.mark.unit
def test_security_md_lists_every_signer_fingerprint(tmp_path: Path) -> None:
    """K7: the published document is the trust anchor for every key in the file.

    ``SECURITY.md`` is what a verifier compares a signature against; the copy of
    ``scripts/deploy/allowed_signers`` inside a tagged tree can be written by
    whoever wrote the tag. So every non-comment key line must have its
    ``ssh-keygen -lf`` fingerprint published there.
    """
    keys = []
    for line in _key_lines():
        _, _, key_type, key = _split(line)
        keys.append(f"{key_type} {key}")
    assert keys, "the signers file has no key lines"

    pub = tmp_path / "signers.pub"
    pub.write_text("\n".join(keys) + "\n", encoding="utf-8")
    listed = _run(tmp_path, "ssh-keygen", "-lf", str(pub))
    assert listed.returncode == 0, listed.stderr

    fingerprints = [line.split()[1] for line in listed.stdout.splitlines() if line.strip()]
    assert len(fingerprints) == len(keys), listed.stdout

    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    missing = [fp for fp in fingerprints if fp not in security]
    assert not missing, f"SECURITY.md does not publish {len(missing)} signer fingerprint(s)"


@pytest.mark.unit
def test_promotion_key_is_absent() -> None:
    assert PROMOTION_KEY not in SIGNERS.read_text()


@pytest.mark.unit
def test_security_md_records_the_unverified_historical_tag() -> None:
    """``r0-v0.1.0`` is named, superseded and explicitly not a trust anchor.

    That tag was cut with the bootstrap promotion key before the signer policy
    existed, so it cannot verify against this file. A verifier who reads
    ``SECURITY.md`` has to learn that before it meets the failure; otherwise a
    "good signature" from an unlisted key is the only thing it has to go on.
    """
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    section = security.split("## Release signing keys", 1)[1].split("\n## ", 1)[0]
    assert "r0-v0.1.0" in section
    assert "r0-v0.1.2" in section, "the historical tag must name its successor"
    assert "not** a current trust anchor" in section
    assert PROMOTION_KEY not in SIGNERS.read_text()


#: The split repos carry their own copy of the signers file (K1/K2 synced it).
#: They are private, so this reads them through the host `gh` session and skips
#: cleanly when that session (or CI) cannot see them.
SPLIT_SIGNERS = (
    ("digithings-ai/digiquant-strategies", "R1"),
    ("digithings-ai/digichat-tenants", "R6"),
)


@pytest.mark.integration
@pytest.mark.parametrize(("repo", "label"), SPLIT_SIGNERS)
def test_promotion_key_is_absent_from_split_repos(repo: str, label: str) -> None:
    if shutil.which("gh") is None:
        pytest.skip("gh CLI unavailable")
    read = _run(
        ROOT,
        "gh",
        "api",
        f"repos/{repo}/contents/allowed_signers",
        "--jq",
        ".content",
        timeout=30,
    )
    if read.returncode != 0:
        pytest.skip(f"cannot read {label} allowed_signers: {read.stderr.strip()}")
    text = base64.b64decode(read.stdout).decode("utf-8")
    assert PROMOTION_KEY not in text, f"promotion key present in {label} allowed_signers"
    assert "release@digithings" in text, f"{label} allowed_signers has no release key"


@pytest.mark.unit
def test_allowed_signers_never_contains_a_private_key() -> None:
    text = SIGNERS.read_text()
    assert "PRIVATE KEY" not in text


@pytest.mark.unit
def test_software_key_has_valid_before() -> None:
    lines = _key_lines()
    software = [line for line in lines if not _is_hardware(line)]
    assert software, "expected the software fallback key to still be listed"
    for line in software:
        _, options, _, _ = _split(line)
        assert "valid-before" in options, f"software key without valid-before: {line!r}"
        assert _as_date(options["valid-before"]) >= _as_date(VALID_BEFORE)


@pytest.mark.unit
def test_key_bounds_are_the_reviewed_set() -> None:
    bounds = []
    for line in _key_lines():
        _, options, _, _ = _split(line)
        bounds.append(_as_date(options["valid-before"]))
    assert sorted(bounds) == sorted([_as_date(VALID_BEFORE), _as_date(NEW_VALID_BEFORE)])


@pytest.mark.unit
def test_tag_signed_before_valid_before_verifies(
    signed_tag_setup: tuple[Path, Path],
) -> None:
    repo, signers = signed_tag_setup
    signed = _sign_tag(repo, "before-v1", "2026-11-01T00:00:00Z")
    assert signed.returncode == 0, signed.stderr

    verified = _verify(repo, signers, "before-v1")
    assert verified.returncode == 0, verified.stdout + verified.stderr
    assert 'Good "git" signature' in verified.stdout + verified.stderr


@pytest.mark.unit
def test_tag_signed_after_valid_before_fails(
    signed_tag_setup: tuple[Path, Path],
) -> None:
    repo, signers = signed_tag_setup
    signed = _sign_tag(repo, "after-v1", "2026-12-05T00:00:00Z")
    assert signed.returncode == 0, signed.stderr

    verified = _verify(repo, signers, "after-v1")
    assert verified.returncode != 0, "a tag cut after valid-before was accepted"
    output = verified.stdout + verified.stderr
    assert "key has expired" in output or "No principal matched" in output, output


@pytest.mark.integration
@pytest.mark.parametrize(("url", "tag"), RELEASE_TAGS)
def test_existing_tags_still_verify(tmp_path: Path, url: str, tag: str) -> None:
    """Adding the bound must not invalidate a tag cut before it (F1 acceptance)."""
    bare = tmp_path / "tags.git"
    init = _run(tmp_path, "git", "init", "--bare", "-q", str(bare))
    assert init.returncode == 0, init.stderr

    try:
        fetched = _run(
            bare,
            "git",
            "fetch",
            "--no-tags",
            "--depth=1",
            "--filter=tree:0",
            url,
            f"refs/tags/{tag}:refs/tags/{tag}",
            env=os.environ | {"GIT_TERMINAL_PROMPT": "0"},
            timeout=30,
        )
    except subprocess.TimeoutExpired:  # pragma: no cover - offline or slow network
        pytest.skip(f"network unavailable: timed out fetching {tag}")
    if fetched.returncode != 0:  # pragma: no cover - offline
        pytest.skip(f"network unavailable: cannot fetch {tag}: {fetched.stderr.strip()}")
    assert fetched.stdout + fetched.stderr, "git fetch produced no output"

    tagger = _run(bare, "git", "for-each-ref", "--format=%(taggerdate:unix)", f"refs/tags/{tag}")
    assert tagger.returncode == 0, tagger.stderr
    bound = datetime.strptime(VALID_BEFORE, "%Y%m%dZ").replace(tzinfo=UTC).timestamp()
    assert int(tagger.stdout.strip()) < bound, (
        f"{tag} was cut after valid-before; this test only covers tags inside the bound"
    )

    verified = _verify(bare, SIGNERS, tag)
    assert verified.returncode == 0, verified.stdout + verified.stderr
    assert 'Good "git" signature' in verified.stdout + verified.stderr
