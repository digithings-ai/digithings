import json, os, urllib.request

issue_id = os.environ["ID"]
api_key = os.environ["PAPERCLIP_API_KEY"]

for suffix in ["", "/cancel", "/status", "/transition"]:
    for method in ["POST", "PATCH"]:
        url = f"http://127.0.0.1:3100/api/issues/{issue_id}{suffix}"
        data = json.dumps({"status": "cancelled"}).encode()
        req = urllib.request.Request(url, data=data, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method=method)
        try:
            with urllib.request.urlopen(req) as r:
                print(method, suffix or "/", r.status)
        except Exception as e:
            print(method, suffix or "/", e)