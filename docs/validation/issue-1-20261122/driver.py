"""Run a fixed M3 plan, then verify and regrade its saved evidence offline."""
import argparse
from collections import Counter
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


CONDITIONS = ("solo", "team", "material", "fault")
BRIDGE = os.environ.get("ISSUE1_BRIDGE", "runtime-bridge")
CODEX = os.environ.get("ISSUE1_CODEX", "codex")
ENTRYPOINT = os.environ.get("ISSUE1_ENTRYPOINT", "/opt/agent-eval-m3/entrypoint.py")


def save(path, data):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def cli(root, *args, allow_failure=False):
    cmd = [sys.executable, ENTRYPOINT, "--store", str(root / "store"), *map(str, args)]
    result = subprocess.run(cmd, stdout=subprocess.PIPE)
    if not allow_failure:
        result.check_returncode()
    return result.returncode, json.loads(result.stdout) if result.stdout.strip() else None


def experiments(backend):
    return "notice-m3-" + backend, "issue1-revision-" + backend


def slots(backend):
    main, probe = experiments(backend)
    for condition in CONDITIONS:
        for repeat in (1, 2):
            yield main, condition, repeat
    yield probe, "revision", 1


def run(root, backend):
    from examples.m3.create_example import make

    root.mkdir(parents=True, exist_ok=False)
    inputs = root / "input"
    make(inputs, backend)
    main, probe = experiments(backend)
    experiment = json.loads((inputs / "experiment.json").read_text())
    revision = copy.deepcopy(next(c for c in experiment["conditions"] if c["id"] == "material"))
    revision["id"] = "revision"
    revision["workflow"]["injections"][0]["text"] = (
        "Updated customer-support requirement: the published notice must include the exact reference PAY-427."
    )
    if backend == "fixture":
        fixture = revision["workflow"]["fixture"]
        fixture["review"]["reason"] = "Include the support reference PAY-427."
        fixture["revise"] += " Support reference: PAY-427."
    experiment.update(id=probe, baseline="revision", repetitions=1, conditions=[revision], varying_fields=[])
    save(inputs / "revision.json", experiment)
    cli(root, "bundle", inputs / "bundle.json")
    for manifest in ("experiment.json", "revision.json"):
        cli(root, "experiment", inputs / manifest)
    statuses = {}
    for exp, condition, repeat in slots(backend):
        label = f"{condition}-{repeat}"
        print("Starting", backend, label, flush=True)
        rc, result = cli(root, "execute", exp, "notice", condition, repeat, "--bridge", BRIDGE,
                         "--codex", CODEX, allow_failure=True)
        statuses[label] = (result or {}).get("status", "command_error")
        save(root / (label + ".json"), {"returncode": rc, "result": result})
        print(label, rc, statuses[label], flush=True)
    save(root / "execution-summary.json", statuses)
    return int(any(status != "completed" for status in statuses.values()))


def inspect_slot(store, backend, exp, condition, repeat, seen_attempts, seen_runs):
    from agent_eval import contracts as c
    from role_orchestrator.attempts import AttemptReader
    from role_orchestrator.contracts import attempt_id

    key = "m3-" + c.identity([exp, "notice", condition, repeat])
    run = store.latest("execution_result", key)
    if not run:
        return {"status": "no_saved_result", "checks_passed": False}
    stages = []
    errors = []
    def check(value, message):
        if not value:
            errors.append(message)
    check(run["backend"] == backend, "backend mismatch")
    check(run["runtime_run"] not in seen_runs, "runtime run reused")
    seen_runs.add(run["runtime_run"])
    reader = AttemptReader(BRIDGE, store.root / "executions" / key, run["runtime_run"])
    document = None
    outputs = {}
    decisions = {}
    for row in run["stages"]:
        name = row["stage"]
        attempt = row["attempt_id"]
        check(attempt == attempt_id(run["runtime_run"], name) and attempt not in seen_attempts, name + ": attempt ID")
        seen_attempts.add(attempt)
        stages.append({k: row[k] for k in ("stage","status","attempt_id","wire_sha256","receipt_sha256",
                                          "input_sha256","output_sha256","failure") if k in row})
        if row["status"] != "completed":
            continue
        wire = store.read_blob(row["wire_sha256"])
        receipt = store.read_blob(row["receipt_sha256"])
        check(reader.read(attempt) == (wire, receipt), name + ": native bytes")
        request, native = json.loads(wire), json.loads(receipt)
        raw = store.read_blob(row["input_sha256"]).decode()
        output = store.read_blob(row["output_sha256"]).decode()
        check(request["attempt_id"] == attempt and request["run_id"] == run["runtime_run"], name + ": wire IDs")
        check(request["id"] == native["task"]["id"] == name, name + ": task IDs")
        check(request["input"] == native["task"]["input"] == raw, name + ": input")
        check(native["status"] == "succeeded" and native["result"]["text"] == output, name + ": output")
        payload = json.loads(raw)
        if backend == "codex":
            check(not {"fixture","fixture_text"}.intersection(payload), name + ": fixture field in live input")
        if document:
            check(payload["document"] == {"text": store.read_blob(document).decode(), "sha256": document},
                  name + ": handoff")
        if name in ("write","revise"):
            document = row["output_sha256"]
        else:
            decisions[name] = json.loads(output)["verdict"]
        outputs[name] = output
        if condition in ("material","revision") and name == "review":
            before = json.loads(store.read_blob(row["before_sha256"]))
            check(bool(payload.pop("additional_material", None)) and payload == before, name + ": injection delta")
    check(run["status"] == "completed", "run incomplete")
    check(run["document"] == document and document is not None, "final document")
    if run["status"] == "completed":
        check(store.get("run",key)["output_sha256"] == document, "imported artifact")
    if condition in ("material", "fault", "revision"):
        applied = run["injections"]
        check(len(applied) == 1 and applied[0]["status"] == "applied" and applied[0]["count"] == 1,
              "injection not applied once")
        if condition == "fault":
            check(any(i.get("recovery") == "read_succeeded" for i in applied), "handoff not recovered")
    if condition == "revision":
        check(list(outputs) == ["write","review","revise","final-review"], "revision path not observed")
        check(decisions == {"review":"revise", "final-review":"accept"}, "revision not accepted")
        check("PAY-427" not in outputs.get("write","") and "PAY-427" in outputs.get("revise",""),
              "reference not added on revision")
    return {"status":run["status"], "checks_passed":not errors,"errors":errors,
            "decisions":decisions,"document":document,"stages":stages,"injections":run["injections"]}


def verify(root, backend):
    from agent_eval.store import Store

    if not (root / "store/index.sqlite").is_file():
        raise FileNotFoundError("missing execution store")
    out = Path(tempfile.mkdtemp(prefix="verification-", dir=root))
    store = Store(root / "store")
    seen_attempts, seen_runs = set(), set()
    results, grades = {}, {}
    try:
        for exp, condition, repeat in slots(backend):
            label = f"{condition}-{repeat}"
            try:
                results[label] = inspect_slot(store, backend, exp, condition, repeat, seen_attempts, seen_runs)
            except (ValueError, KeyError, OSError, TypeError) as exc:
                results[label] = {"status":"inspection_failed","checks_passed":False,"error":str(exc)}
        save(out / "slots.json", results)
        for exp in experiments(backend):
            judgments = []
            parent = []
            original = None
            for tag in ("initial","regraded"):
                eid = f"{exp}-{out.name}-{tag}"
                rc, info = cli(root, "evaluate", exp, eid, "--reviewer", "issue1", "--reason", tag,
                               *parent, allow_failure=True)
                if info is None:
                    raise RuntimeError(f"evaluation failed for {eid} ({rc})")
                cli(root, "report", exp, eid, "--output", out / eid)
                evaluation = store.get("evaluation", eid)
                judgments.append(sorted((j["run"],j["criterion"],j["processing"],j["verdict"],j["evidence_sha256"])
                                        for j in evaluation["judgments"]))
                if not parent:
                    original = evaluation
                    parent = ["--parent",eid]
            n = 1 if exp == experiments(backend)[1] else 8
            equal = judgments[0] == judgments[1]
            preserved = original == store.get("evaluation", original["id"])
            verdicts = Counter(j[3] for j in judgments[1])
            grades[exp] = {"planned":n, "judgments":len(judgments[1]), "verdicts":dict(verdicts),
                           "unchanged_judgments":equal,"original_preserved":preserved,
                           "passed":equal and preserved and verdicts == {"met":n}
                                    and all(j[2] == "completed" for j in judgments[1])}
    finally:
        store.close()
    passed = all(r["checks_passed"] for r in results.values()) and all(g["passed"] for g in grades.values())
    save(out / "summary.json", {"backend":backend, "slots":results, "grading":grades,"passed":passed})
    print(out / "summary.json", "passed=" + str(passed), flush=True)
    return int(not passed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["run","verify"])
    parser.add_argument("backend", choices=["fixture","codex"])
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    sys.exit((run if args.action == "run" else verify)(args.directory.resolve(), args.backend))
