import json, os, urllib.request
BASE="http://localhost:3100/api"
K=os.environ["PAPERCLIP_API_KEY"]
C=os.environ["PAPERCLIP_COMPANY_ID"]
def get(p):
    r=urllib.request.Request(BASE+p, headers={"Authorization":"Bearer "+K})
    with urllib.request.urlopen(r) as f: return json.load(f)
def post(p, body, raw=False):
    d=json.dumps(body).encode()
    r=urllib.request.Request(BASE+p, data=d, headers={"Authorization":"Bearer "+K,"Content-Type":"application/json"}, method="POST")
    try:
        with urllib.request.urlopen(r) as f: return f.status, json.loads(f.read().decode() or "{}")
    except urllib.error.HTTPError as e: return e.code, e.read().decode()[:400]
def patch(p, body):
    d=json.dumps(body).encode()
    r=urllib.request.Request(BASE+p, data=d, headers={"Authorization":"Bearer "+K,"Content-Type":"application/json"}, method="PATCH")
    try:
        with urllib.request.urlopen(r) as f: return f.status, json.loads(f.read().decode() or "{}")
    except urllib.error.HTTPError as e: return e.code, e.read().decode()[:400]
