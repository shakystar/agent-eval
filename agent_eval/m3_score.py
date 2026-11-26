import argparse
import fcntl
import json
import os
import re
from pathlib import Path


_CASE = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}"
_IDENTITY = ("run_id", "attempt_id")
_PLAN = (*_IDENTITY, "task_id", "member_id", "expected_role_version")
_ROW = ("assignment", "run", "attempt", "thread", "rpc_id", "request_sha256")


def observe(bridge, state, ids, plan):
    from role_orchestrator.assignment import observe as native_observe
    return native_observe(bridge, state, ids, plan)


def verify_m1(observations, *, assignment_id, member_id, role_version):
    from role_orchestrator.m1_evidence import verify_m1 as native_verify_m1
    return native_verify_m1(observations, assignment_id=assignment_id,
                            member_id=member_id, role_version=role_version)


def _decision(action, reason):
    return {"action": action, "reason": reason}


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("invalid JSON constant")


def _json(data):
    value = json.loads(data.decode("utf-8"), object_pairs_hook=_object,
                       parse_constant=_constant)
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    return value


def _valid_row(row):
    kind = row.get("kind")
    if kind not in ("start", "ack"):
        return False
    keys = {"kind", "ordinal", *_ROW}
    if kind == "ack":
        keys.add("turn")
    return (row.keys() == keys
            and type(row["ordinal"]) is int and row["ordinal"] > 0
            and all(_nonempty(row[k]) for k in ("assignment", "run", "attempt", "thread"))
            and isinstance(row["rpc_id"], str) and _sha(row["request_sha256"])
            and (kind == "start" or _nonempty(row["turn"])))


def _ledger_rows(raw, slot):
    *lines, tail = raw.split(b"\n")
    invalid = bool(tail)
    rows = []
    for line in lines:
        try:
            row = _json(line)
        except ValueError:
            invalid = True
            continue
        if _valid_row(row):
            rows.append(row)
        else:
            invalid = True
    # Count attributable starts across all attempts before filtering by attempt.
    if sum(r["kind"] == "start" and r["assignment"] == slot for r in rows) > 1:
        return _decision("reject", "duplicate_starts"), None, None
    if (invalid or not 1 <= len(rows) <= 2
            or rows[0]["kind"] != "start" or rows[0]["ordinal"] != 1
            or rows[0]["assignment"] != slot):
        return _decision("hold", "missing_invalid_or_mixed_ledger"), None, None
    start = rows[0]
    ack = rows[1] if len(rows) == 2 else None
    if ack is not None and (ack["kind"] != "ack"
                            or any(ack[k] != start[k] for k in ("ordinal", *_ROW))):
        return _decision("hold", "ack_not_bound_to_start"), None, None
    return None, start, ack


def _observe_bound(bridge, state, plan, start, ack):
    ids = {k: plan[k] for k in _IDENTITY}
    if (start["run"], start["attempt"]) != (ids["run_id"], ids["attempt_id"]):
        return _decision("hold", "start_not_bound_to_plan"), None
    native = observe(bridge, state, ids, plan)
    # The native reader is already pinned to ids; check echoed IDs only if present.
    if not isinstance(native, dict) or any(k in native and native[k] != v
                                           for k, v in ids.items()):
        return _decision("hold", "native_identity_not_bound"), None
    evidence = native.get("turn_evidence")
    task = plan["task_id"]
    if evidence is not None and (not isinstance(evidence, dict)
                                 or evidence.get("assignment_id") != task):
        return _decision("hold", "native_task_not_bound"), None
    turn = evidence.get("turn") if evidence else None
    if turn is not None and (not isinstance(turn, dict)
                             or (ack is not None and (turn.get("session"), turn.get("turn_id"))
                                 != (ack["thread"], ack["turn"]))):
        return _decision("hold", "native_turn_not_bound"), None
    succeeded = native.get("status") == "succeeded"
    receipt = native.get("receipt_sha256")
    if succeeded and (ack is None or turn is None or not _sha(receipt)):
        return _decision("hold", "missing_ack_turn_or_receipt"), None
    verified = verify_m1([native], assignment_id=task, member_id=plan["member_id"],
                         role_version=plan["expected_role_version"])
    action = verified["action"]
    if action == "reject":
        return _decision("reject", "native_verifier_rejected"), None
    if action != "accept" or not succeeded:
        return _decision("hold", "native_success_not_verified"), None
    result = _decision("accept", "verified_single_start")
    result["receipt"] = {**ids, "task_id": task, "receipt_sha256": receipt}
    return result, native


def score_assignment(*, arm, assignment, ledger, state, bridge, plan=None, score=None):
    """Gate one pinned assignment and optionally score its verified observation."""
    scoring = False
    try:
        if (arm not in ("current", "candidate") or not isinstance(assignment, str)
                or not re.fullmatch(rf"{arm}/{_CASE}/(?:0|[1-9][0-9]*)", assignment)):
            return _decision("hold", "invalid_arm_or_assignment")
        ledger = Path(ledger)
        state = Path(state).absolute()
        bridge = Path(bridge).absolute()
        plan_path = Path(plan) if plan is not None else state / "assignment-v2.plan.json"
        lock_path = Path(str(ledger) + ".lock")
        if not lock_path.is_file():
            return _decision("hold", "missing_ledger_lock")
        # Use the recorder's separate owner lock; never create it on the reader path.
        with lock_path.open("rb") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
            if not ledger.is_file():
                return _decision("hold", "missing_ledger")
            decision, start, ack = _ledger_rows(ledger.read_bytes(), assignment)
            if decision is not None:
                return decision
            if not state.is_dir() or not bridge.is_file() or not os.access(bridge, os.X_OK):
                return _decision("hold", "missing_state_or_executable_bridge")
            if not plan_path.is_file():
                return _decision("hold", "missing_plan")
            pinned = _json(plan_path.read_bytes())
            if (not all(_nonempty(pinned.get(k)) for k in _PLAN)
                    or not _sha(pinned.get("input_sha256"))
                    or not isinstance(pinned.get("instruction"), str)):
                return _decision("hold", "invalid_plan_identity")
            result, native = _observe_bound(bridge, state, pinned, start, ack)
            if result["action"] == "accept" and score is not None:
                # Scorer errors propagate, but the callback runs under the lock.
                scoring = True
                result["score"] = score(native)
    except Exception as exc:
        if scoring:
            raise
        if isinstance(exc, BlockingIOError):
            return _decision("hold", "ledger_lock_busy")
        # Even an observer/verifier error must not make a receipt eligible.
        return _decision("hold", "evidence_read_or_verification_failed")
    return result


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def main(argv=None):
    parser = _Parser(description="Gate an M3 native assignment before scoring", allow_abbrev=False)
    parser.add_argument("--arm", required=True, choices=("current", "candidate"))
    parser.add_argument("--case", required=True)
    parser.add_argument("--repeat", required=True, type=int)
    parser.add_argument("--root", required=True)
    parser.add_argument("--bridge", required=True)
    try:
        args = parser.parse_args(argv)
        if not re.fullmatch(_CASE, args.case) or args.repeat < 0:
            parser.error("invalid case or repeat")
    except ValueError:
        result = _decision("hold", "invalid_cli_arguments")
        status = 2
    else:
        assignment = f"{args.arm}/{args.case}/{args.repeat}"
        slot = Path(args.root) / assignment
        result = score_assignment(arm=args.arm, assignment=assignment,
                                  ledger=slot / "ledger.jsonl",
                                  state=slot / "assignment", bridge=args.bridge)
        status = {"accept": 0, "hold": 3, "reject": 4}[result["action"]]
    print(json.dumps(result, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
