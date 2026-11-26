"""Replay an M2 synthetic research route in a new directory. See M2-results.md."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

REVISION = "112d4629d4261b4403ff33fbde43e36431c435f4"
CATALOG = "07740a6559664d6ace4f6c6fd8dad328432bca3c73d2b640f556801d9c0994f7"


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def replay(args):
    root = args.state.resolve()
    root.mkdir(mode=0o700)
    state = root / "checkpoint"
    state.mkdir(mode=0o700)
    bindir = root / "bin"
    bindir.mkdir()
    executable = bindir / "codex"
    shutil.copyfile(Path(__file__).with_name("peer.py"), executable)
    executable.chmod(0o700)
    ledger = root / "dispatches.jsonl"
    fixture = args.fixture.resolve()
    case = json.loads(fixture.read_bytes())["case"]
    require(case["synthetic"] is True, "Expected synthetic case")
    if args.fault == "author":
        case["contributors"].append("acl-025")
    if args.fault == "other":
        require(len(args.other_packet) == 64, "Supply the other route's packet digest")
    repo = args.orchestrator.resolve()
    env = dict(os.environ, M2_LEDGER=str(ledger), M2_FIXTURE=str(fixture),
               M2_USAGE_CASE=args.usage_case, M2_FAULT=args.fault, M2_OTHER_PACKET=args.other_packet,
               PYTHONPATH=str(repo), PATH=str(bindir) + os.pathsep + os.environ["PATH"])
    command = [sys.executable, "-m", "role_orchestrator.research_handoff",
               "--lab", str(args.lab.resolve()), "--revision", REVISION,
               "--runtime", str(args.bridge.resolve()), "--state", str(state),
               "--research-goal", "study", "--planning-team", "planning",
               "--planning-goal", "intake", "--catalog-sha256", CATALOG, "--backend", "codex"]

    if args.usage_case:
        sys.path.insert(0, str(repo))
        from role_orchestrator.m1_evidence import verify_m1

    def invoke(payload):
        raw = subprocess.check_output(command, input=payload, cwd=repo, env=env, timeout=140)
        return json.loads(raw)

    result = invoke(canonical({"case": case}))
    events = [json.loads(line) for line in ledger.read_text().splitlines()]
    phases = [event[0] for event in events]
    receipts = result["receipts"]
    require(len(events) == len(receipts), "Unaccounted synthetic dispatch")
    for index, (phase, thread, turn) in enumerate(events):
        ref = receipts[phase]
        task = state / ref["task_id"]
        plan = json.loads((task / "assignment-v2.plan.json").read_bytes())
        verdict = json.loads((task / "assignment-v2.verdict.json").read_bytes())
        native_file, = (task / "runtime/tasks").glob("*.json")
        raw = native_file.read_bytes()
        native = json.loads(raw)
        context = json.loads(native["task"]["input"])["context"]
        require(ref["receipt_sha256"] == hashlib.sha256(raw).hexdigest()
                == verdict["receipt_sha256"], "Receipt hash mismatch")
        require(ref["run_id"] == verdict["run_id"] == plan["run_id"]
                and ref["attempt_id"] == verdict["attempt_id"] == plan["attempt_id"],
                "Attempt mismatch")
        require(ref["member_id"] == verdict["actual_member_id"]
                and ref["role_version"] == verdict["actual_role_version"], "Reviewer mismatch")
        require(context["receipts"] == {name: receipts[name] for name in phases[:index]},
                "Predecessor receipt mismatch")
        require(context["case_sha256"] == hashlib.sha256(canonical(case)).hexdigest()
                and context["case"]["id"] == ref["case_id"] == case["id"]
                and context["phase"] == phase, "Case or phase mismatch")
        observed = verdict["turn_evidence"]["turn"]
        require(native["result"]["session"] == observed["session"] == thread
                and native["result"]["turn_id"] == observed["turn_id"] == turn, "Turn mismatch")
        require(verdict["artifact"]["output_sha256"]
                == hashlib.sha256(native["result"]["text"].encode()).hexdigest(), "Output mismatch")
        if args.usage_case:
            measured = args.usage_case == "zero"
            usage = {"input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0}
            require(native["result"].get("turn_usage") == (usage if measured else None),
                    "Unexpected native usage for " + args.usage_case)
            check = verify_m1([verdict], assignment_id=ref["task_id"],
                              member_id=ref["member_id"], role_version=ref["role_version"])
            require(check["turn_count"] == 1 and check["usage_complete"] is measured
                    and check["action"] == ("accept" if measured else "hold")
                    and check["status"] == ("verified" if measured else "uncertain"),
                    "Unexpected usage verdict for " + args.usage_case)
        if phase in ("review", "synthesize"):
            prior = context["prior"]
            require(prior["draft_sha256"] == hashlib.sha256(canonical(prior["draft"])).hexdigest(),
                    "Draft mismatch")
        if phase == "decision" and not args.fault:
            require(result["branch"] == verdict["artifact"]["payload"]["decision"]
                    and result["branch"]["packet_sha256"] == context["prior"]["packet_sha256"],
                    "Final decision mismatch")

    before = ledger.read_bytes()
    require(invoke(b"") == result and ledger.read_bytes() == before, "Replay dispatched new work")
    branch = result["branch"]
    if not args.fault:
        require(len(receipts) == (5 if case["kind"] == "request" else 6)
                and "decision" in receipts, "Incomplete route")
    elif args.fault in ("author", "self"):
        require(branch["action"] == "reassign", "Reassignment not requested")
        require(("review" in receipts) == (args.fault == "self"), "Unexpected review dispatch")
        if args.fault == "self":
            require(result["data"]["review"]["conflict"] is True, "Conflict was lost")
    else:
        require(branch["action"] == "hold" and branch["terminal"], "Invalid reference accepted")
    return {"case": case["id"], "dispatches": len(events), "replay_new_turns": 0, "branch": branch}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("orchestrator", "bridge", "lab", "fixture", "state"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--fault", choices=("author", "self", "stale", "other"), default="")
    parser.add_argument("--usage-case", choices=("missing-last", "missing-counter", "zero"),
                        default="", help="Verify receipt and verdict for the injected usage event")
    parser.add_argument("--other-packet", default="")
    print(json.dumps(replay(parser.parse_args()), ensure_ascii=False))
