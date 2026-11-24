"""Recheck saved assignment plans against native attempt receipts, without dispatch."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from role_orchestrator.assignment import PLAN, observe
from role_orchestrator.attempts import AttemptReader


def inspect(state, runtime):
    records = []
    for path in sorted(state.rglob(PLAN)):
        stage = path.parent
        plan = json.loads(path.read_bytes())
        ids = {key: plan[key] for key in ("run_id", "attempt_id")}
        pair = AttemptReader(runtime, stage, ids["run_id"]).read(ids["attempt_id"])
        verdict = observe(runtime, stage, ids, plan)
        record = {
            "task_id": plan["task_id"],
            "member_id": plan["member_id"],
            "role": plan["handoff_id"],
            **ids,
            "backend": plan["backend"],
            "lab_sha": plan["revision"],
            "requested": plan["desired"],
            "status": verdict["status"],
            "input_sha256": plan["input_sha256"],
            "contract_sha256": plan["contract"]["sha256"],
        }
        if pair:
            wire, receipt = pair
            record["wire_sha256"] = sha256(wire).hexdigest()
            record["receipt_sha256"] = sha256(receipt).hexdigest()
            if verdict.get("receipt_sha256") != record["receipt_sha256"]:
                raise ValueError(f"unbound receipt in {stage.name}")
        if "artifact" in verdict:
            record["output_sha256"] = verdict["artifact"]["output_sha256"]
        if "reason" in verdict:
            record["reason"] = verdict["reason"]
        records.append(record)
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", type=Path)
    parser.add_argument("runtime")
    args = parser.parse_args()
    print(json.dumps(inspect(args.state, args.runtime), indent=2))
