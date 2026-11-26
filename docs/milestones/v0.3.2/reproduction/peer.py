#!/usr/bin/env python3
"""Synthetic app-server peer for the pinned research cases. Uses stdio only."""
import json
import os
from pathlib import Path
import sys
import uuid


def send(message):
    print(json.dumps(message, ensure_ascii=False), flush=True)


def reply(request_id, result):
    send({"id": request_id, "result": result})


def complete_turn(request_id, params):
    context = json.loads(params["input"][0]["text"])["context"]
    phase = context["phase"]
    fixture = json.loads(Path(os.environ["M2_FIXTURE"]).read_bytes())
    envelope = fixture["fixtures"][phase]
    body, = envelope.values()
    for key in ("case_sha256", "draft_sha256", "packet_sha256"):
        if key in body:
            body[key] = context[key] if key == "case_sha256" else context["prior"][key]

    fault = os.environ.get("M2_FAULT")
    if phase == "review" and fault == "self":
        body.update(conflict=True, opinions={})
    elif phase == "review" and fault == "stale":
        body["draft_sha256"] = "0" * 64
    elif phase == "decision" and fault == "other":
        body["packet_sha256"] = os.environ["M2_OTHER_PACKET"]

    thread = params["threadId"]
    turn = str(uuid.uuid4())
    with Path(os.environ["M2_LEDGER"]).open("a", encoding="utf-8") as ledger:
        print(json.dumps([phase, thread, turn]), file=ledger)
    reply(request_id, {"turn": {"id": turn, "status": "inProgress"}})
    usage = {"inputTokens": 10, "outputTokens": 3, "cachedInputTokens": 2}
    usage_case = os.environ.get("M2_USAGE_CASE")
    token_usage = {"last": usage}
    if usage_case:
        usage.update(dict.fromkeys(usage, 0))
        if usage_case == "missing-counter":
            del usage["outputTokens"]
        elif usage_case == "missing-last":
            del token_usage["last"]
    send({"method": "thread/tokenUsage/updated", "params": {
        "threadId": thread, "turnId": turn, "tokenUsage": token_usage
    }})
    message = {"type": "agentMessage", "phase": "final_answer",
               "text": json.dumps(envelope, ensure_ascii=False)}
    send({"method": "turn/completed", "params": {
        "threadId": thread, "turn": {"id": turn, "status": "completed", "items": [message]}
    }})


def main():
    if sys.argv[1:2] != ["app-server"]:
        raise SystemExit("Expected app-server subcommand")
    for line in sys.stdin:
        request = json.loads(line)
        if "id" not in request:
            continue
        method = request["method"]
        params = request.get("params", {})
        if method == "turn/start":
            complete_turn(request["id"], params)
            continue
        if method == "account/read":
            result = {"account": {"type": "chatgpt"}, "requiresOpenaiAuth": True}
        elif method in ("thread/start", "thread/resume"):
            result = {"thread": {"id": params.get("threadId") or str(uuid.uuid4()),
                                 "cwd": params["cwd"]}}
        elif method == "thread/loaded/list":
            result = {"data": []}
        elif method == "thread/unsubscribe":
            result = {"status": "unsubscribed"}
        else:
            result = {}
        reply(request["id"], result)


if __name__ == "__main__":
    main()
