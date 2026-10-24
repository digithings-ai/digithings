import json, os, urllib.request

issue_id = os.environ["ID"]
api_key = os.environ["PAPERCLIP_API_KEY"]
base = f"http://127.0.0.1:3100/api/issues/{issue_id}"

payload = {"status": "cancelled"}
data = json.dumps(payload).encode()
req = urllib.request.Request(base, data=data, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="PATCH")
try:
    with urllib.request.urlopen(req) as r:
        print(payload, "->", r.status)
except Exception as e:
    print(payload, "->", e)