#!/usr/bin/env python3
"""Test-only send-side fault. Forward one copy to an additional offline peer before forwarding the original."""
import json
from pathlib import Path
import subprocess
import sys

cmd=[str(Path(__file__).with_name('peer.py')),'app-server']
with subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=sys.stdout.buffer) as regular:
    for line in sys.stdin.buffer:
        if json.loads(line).get('method')=='turn/start':
            injected=subprocess.run(cmd,input=line,capture_output=True,check=True,timeout=15)
            Path(__import__('os').environ['PREFLIGHT_CASE'],'extra-reply.jsonl').write_bytes(injected.stdout)
        regular.stdin.write(line)
        regular.stdin.flush()
    regular.stdin.close()
