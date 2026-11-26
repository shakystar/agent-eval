"""Check M3 admission for both arms using a fixed synthetic role output and no model."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

KIT = Path(__file__).resolve().parent
REVISION = "112d4629d4261b4403ff33fbde43e36431c435f4"
EXPECTED = {"success": (0, "accept"), "lost": (3, "hold"), "double": (4, "reject")}


def verify(args, arm, mode):
    case = args.output / (arm + "-" + mode)
    case.mkdir()
    (case / "release").touch()
    root = args.output / "slots"
    slot = root / arm / mode / "1"
    backend = args.output / "codex"
    reply = {"existing_evidence": "synthetic", "base_sha": "1" * 40, "tests": [], "unverified": []}
    env = dict(os.environ, PREFLIGHT_CASE=str(case), PREFLIGHT_MODE=mode,
               PREFLIGHT_REPLY=json.dumps(reply), PREFLIGHT_BRIDGE=str(args.bridge))
    bridge = KIT / "admission_fault.py" if mode == "double" else args.bridge
    cmd = [sys.executable, "-m", "agent_eval.m3_assignment", "--root", str(root),
           "--arm", arm, "--case", mode, "--repeat", "1", "--backend-executable", str(backend),
           "--", "--lab", str(args.lab), "--revision", REVISION, "--runtime", str(bridge),
           "--member", "acl-006", "--task", "m3-synthetic", "--profile", "lab-v1"]
    inputs = json.dumps(dict(identity={}, windows={}, approved_vectors={}, source={}))
    first = subprocess.run(cmd, env=env, input=inputs, capture_output=True, text=True, timeout=60)
    score_cmd = [sys.executable, "-m", "agent_eval.m3_score", "--root", str(root), "--arm", arm,
                 "--case", mode, "--repeat", "1", "--bridge", str(args.bridge)]
    scored = subprocess.run(score_cmd, env=env, capture_output=True, text=True, timeout=20)
    code, action = EXPECTED[mode]
    if (first.returncode, scored.returncode) != (code, code) or json.loads(scored.stdout)["action"] != action:
        raise RuntimeError((arm, mode, first.stdout, first.stderr, scored.stdout, scored.stderr))
    ledger = (slot / "ledger.jsonl").read_bytes()
    rows = [json.loads(line) for line in ledger.splitlines()]
    starts = [row for row in rows if row["kind"] == "start"]
    peer_log = case / "calls.jsonl"
    calls = peer_log.read_bytes()
    observed = [json.loads(line) for line in calls.splitlines()]
    if len(observed) != (2 if mode == "double" else 1) or [r["request_sha256"] for r in starts] != [
        r["request_sha256"] for r in observed
    ]:
        raise RuntimeError("recorded starts differ from actual peer deliveries")
    retry = subprocess.run(cmd, env=env, input=inputs, capture_output=True, text=True, timeout=20)
    if not retry.returncode or (slot / "ledger.jsonl").read_bytes() != ledger or peer_log.read_bytes() != calls:
        raise RuntimeError("same-slot retry changed call history")
    native = json.loads((slot / "assignment" / "assignment-v2.verdict.json").read_bytes())
    if mode != "lost" and native["status"] != "succeeded":
        raise RuntimeError("expected a successful native receipt for the positive control")
    return dict(arm=arm, mode=mode, native=native["status"], action=action, starts=len(starts),
                recorder_sha256=hashlib.sha256(ledger).hexdigest(), receipt=native.get("receipt_sha256"),
                trial_exit=first.returncode, scoring_exit=scored.returncode, retry_new_calls=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("bridge", "lab", "output"):
        parser.add_argument("--" + name, type=lambda value: Path(value).resolve(), required=True)
    args = parser.parse_args()
    args.output.mkdir(mode=0o700)
    (args.output / "codex").symlink_to(KIT / "peer.py")
    rows = [verify(args, arm, mode) for arm in ("current", "candidate") for mode in EXPECTED]
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
