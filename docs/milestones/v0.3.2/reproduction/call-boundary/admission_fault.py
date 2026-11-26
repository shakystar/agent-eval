#!/usr/bin/env python3
"""Inject one duplicate before the recorder while leaving one answer visible to the adapter."""
import json
import os
import shutil
import subprocess
import sys


def inject():
    with subprocess.Popen([os.environ["PREFLIGHT_RECORDER"], *sys.argv[1:]], stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE) as peer:
        for wire in sys.stdin.buffer:
            request = json.loads(wire)
            start = request.get("method") == "turn/start"
            for visible in ((False, True) if start else (True,)):
                peer.stdin.write(wire)
                peer.stdin.flush()
                if "id" not in request:
                    continue
                for response in peer.stdout:
                    if visible:
                        sys.stdout.buffer.write(response)
                        sys.stdout.buffer.flush()
                    msg = json.loads(response)
                    if start and msg.get("method") == "turn/completed":
                        break
                    if not start and msg.get("id") == request["id"]:
                        break
                else:
                    raise RuntimeError("synthetic peer closed before reply")
        peer.stdin.close()


if __name__ == "__main__":
    if sys.argv[1:2] == ["app-server"]:
        inject()
    else:
        args = sys.argv[1:]
        if "--codex" in args:
            index = args.index("--codex") + 1
            os.environ["PREFLIGHT_RECORDER"] = shutil.which(args[index])
            args[index] = os.path.abspath(__file__)
        bridge = os.environ["PREFLIGHT_BRIDGE"]
        os.execv(bridge, [bridge, *args])
