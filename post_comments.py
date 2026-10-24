import json, os, urllib.request

batch = os.environ["BATCH"]
agent = "6f361355-e086-4a53-a913-b5811e099ab0"
run = "261482bc-7757-4c6a-af8d-082eecb64d52"
heads = {
    5441: "2be04cb07a633dc832eed227660ab7304b56090a",
    6169: "367c64204ea32fb6cd99ae9baf582af5197f0a21",
    6263: "177278b680f49a9ddff42613f19080d73dbc7eb5",
    6272: "c907712c5251b00947398c4122b4032154242d11",
    6273: "74004541091bd62a642293fc6e1a09a47e044394",
    6291: "87831a3b84f4220c95dacb1de4074296693ef102",
    6300: "8194ad834aec268937aef91ed591c0021ccee98f",
    6307: "b5d825b06e909df7fe9c3e11f72473bfebc5cfcf",
    6311: "cd53c89f2251d846e11d4954d8d0f2e4795548ad",
}
for n, sha in heads.items():
    body = (
        "Review verdict: approved\n\n"
        f"<!-- opencode-power-pack:code-review verdict=approved scope=digithings-ai/digithings#{n}@{sha} -->\n"
        f"<!-- digithings-review agent={agent} run={run} head={sha} -->\n"
        "<!-- in-session-review -->\n\n"
        f"digithings#{n} (leaf in_review) approved on head `{sha}`. local-ci green, CLEAN. Merge queue may merge."
    )
    data = json.dumps({"body": body}).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:3100/api/issues/{batch}/comments",
        data=data,
        headers={"Authorization": f"Bearer {os.environ['PAPERCLIP_API_KEY']}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        print(n, r.status)
