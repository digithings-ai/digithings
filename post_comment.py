import json, urllib.request, os
API = os.environ['PAPERCLIP_API_URL'].rstrip('/') + '/api'
KEY = os.environ['PAPERCLIP_API_KEY']
IID = '3c34ffc3-6ab3-4741-a46a-2523321e3e01'
W = '/Users/chrisstefan/Code/digithings/.paperclip/worktrees/DIG-3439-develop-maintenance-sweep-every-3h/'
def post(p, body):
    data = json.dumps(body).encode()
    r = urllib.request.Request(API + p, data=data, method='POST',
        headers={'Authorization': 'Bearer ' + KEY, 'Content-Type': 'application/json',
                 'X-Paperclip-Run-Id': os.environ['PAPERCLIP_RUN_ID']})
    with urllib.request.urlopen(r, timeout=30) as resp:
        return resp.status, json.load(resp)
body = open(W + 'run_comment.md').read()
st, resp = post('/issues/%s/comments' % IID, {'body': body})
print('comment POST', st, 'id=', resp.get('id'), flush=True)
