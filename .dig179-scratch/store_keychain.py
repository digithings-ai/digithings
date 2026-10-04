"""DIG-179 scratch helper (untracked, deleted before commit).

Move the Proton credential out of the git blob and into the macOS Keychain
(service `digithings`) WITHOUT the value ever reaching the model's context.

Rules honoured:
  * The value is read from the committed blob inside this process.
  * It is handed to `security(1)` directly via argv (no shell, no xtrace).
  * Nothing secret is printed. Only lengths, names and boolean readback.
  * A readback proves the stored value equals the blob value.
"""
import hashlib
import re
import subprocess
import sys

REPO = "/Users/chrisstefan/digithings-books"
COMMIT = "82122ae6ca942698d39f6a5d823ed4a9e82d53a2"
BLOB_PATH = "inbox/chat/twelve-x/2026-05-28.txt"
SERVICE = "digithings"

# Account names are secret *names* only. No values, no client person names.
ACCOUNTS = {
    "proton.twelve-x.mailbox.pass-a": "credential quoted by the client at 17:56",
    "proton.twelve-x.mailbox.pass-b": "credential confirmed by Chris at 18:19",
}
COMMENT = (
    "DIG-179 interim store (Bitwarden bootstrap pending, DIG-95). "
    "Recovered from a committed chat transcript; live status unconfirmed; "
    "rotate in Proton once a recovery method exists."
)

PASSWORD_KEYWORD = re.compile(r"(?i)\bpassword\b")
ADDRESS_TOKEN = re.compile(r"(\S+@\S+?\.\w+)")


def blob_text() -> str:
    out = subprocess.run(
        ["git", "-C", REPO, "show", f"{COMMIT}:{BLOB_PATH}"],
        check=True,
        capture_output=True,
    )
    return out.stdout.decode("utf-8")


def candidates(text: str) -> list[str]:
    """Return the secret-shaped strings, in file order.

    Two shapes only:
      1. everything after a `password` keyword on that line;
      2. a token that directly follows a bare email address.
    """
    found: list[str] = []
    for line in text.split("\n"):
        keyword = PASSWORD_KEYWORD.search(line)
        if keyword:
            tail = line[keyword.end():].strip()
            if tail:
                found.append(tail)
            continue
        address = ADDRESS_TOKEN.search(line)
        if not address:
            continue
        rest = line[address.end():].strip()
        if not rest or " " in rest:
            continue
        if "@" in rest:
            continue
        found.append(rest)
    return found


def keychain_write(account: str, value: str) -> None:
    subprocess.run(
        [
            "security",
            "add-generic-password",
            "-U",
            "-s",
            SERVICE,
            "-a",
            account,
            "-j",
            COMMENT,
            "-l",
            "digithings — Proton twelve-x mailbox (interim)",
            "-w",
            value,
        ],
        check=True,
        capture_output=True,
    )


def keychain_read(account: str) -> str | None:
    proc = subprocess.run(
        ["security", "find-generic-password", "-s", SERVICE, "-a", account, "-w"],
        capture_output=True,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8").rstrip("\n")


def main() -> int:
    values = candidates(blob_text())
    if len(values) != len(ACCOUNTS):
        print(f"ABORT: expected {len(ACCOUNTS)} credential shapes, found {len(values)}")
        return 1
    print(f"blob {COMMIT[:12]}:{BLOB_PATH}")
    print(f"credential shapes found: {len(values)} (values not printed)")
    for account, value in zip(ACCOUNTS, values):
        keychain_write(account, value)
        readback = keychain_read(account)
        ok = readback == value
        digest = hashlib.sha256(value.encode()).hexdigest()[:12]
        print(
            f"keychain service={SERVICE} account={account} "
            f"len={len(value)} sha256_12={digest} readback_match={ok} "
            f"purpose={ACCOUNTS[account]}"
        )
        if not ok:
            print(f"ABORT: readback mismatch for {account}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
