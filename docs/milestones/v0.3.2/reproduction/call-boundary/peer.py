#!/usr/bin/env python3
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid

root = Path(os.environ['PREFLIGHT_CASE'])
def send(obj):
    print(json.dumps(obj), flush=True)
for line in sys.stdin:
    req = json.loads(line)
    if 'id' not in req:
        continue
    method = req['method']
    params = req.get('params', {})
    result = {}
    if method == 'turn/start':
        turn = str(uuid.uuid4())
        thread = params['threadId']
        event = {'turn': turn, 'thread': thread, 'request_sha256': hashlib.sha256(line.encode()).hexdigest()}
        with (root/'calls.jsonl').open('a') as ledger:
            ledger.write(json.dumps(event) + '\n')
            ledger.flush()
            os.fsync(ledger.fileno())
        (root/'wire.json').write_text(line)
        deadline = time.monotonic()+30
        while not (root/'release').exists():
            if time.monotonic() > deadline:
                sys.exit(2)
            time.sleep(0.02)
        if os.environ['PREFLIGHT_MODE'] == 'lost':
            sys.exit(0)
        send({'id':req['id'], 'result':{'turn':{'id':turn,'status':'inProgress'}}})
        send({'method':'thread/tokenUsage/updated','params':{'threadId':thread,'turnId':turn,'tokenUsage':{'last':{'inputTokens':1,'outputTokens':1,'cachedInputTokens':0}}}})
        send({'method':'turn/completed','params':{'threadId':thread,'turn':{'id':turn,'status':'completed','items':[{'type':'agentMessage','phase':'final_answer','text':os.environ.get('PREFLIGHT_REPLY', 'identical output')}]}}})
        continue
    if method == 'account/read':
        result = {'account':{'type':'chatgpt'},'requiresOpenaiAuth':True}
    elif method in ('thread/start','thread/resume'):
        result = {'thread':{'id':params.get('threadId','thread-synthetic'),'cwd':params['cwd']}}
    elif method == 'thread/loaded/list':
        result = {'data':[]}
    elif method == 'thread/unsubscribe':
        result = {'status':'unsubscribed'}
    send({'id':req['id'],'result':result})
