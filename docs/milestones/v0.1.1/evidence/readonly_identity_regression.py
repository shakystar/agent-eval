"""Run from an isolated orchestrator checkout with its Python dependencies installed."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    plan = dict(slot="document", required_fields=["text"])
    for position, member in (("producer", "acl-007"), ("consumer", "acl-005")):
        plan[position] = dict(member=member, instruction="Inspect a document",
                              model="gpt-6.2-sol", effort="medium")
    with tempfile.TemporaryDirectory() as directory:
        state = Path(directory)
        command = [sys.executable, "-m", "role_orchestrator.handoff_runner",
                   "--state", str(state), "--runtime", "/bin/true", "--backend", "fixture"]

        def invoke(operation, **fields):
            return subprocess.run(command, text=True, capture_output=True, timeout=10,
                                  input=json.dumps(dict(plan=plan, op=operation, **fields)))

        publish = invoke("publish-initial", payload={"text": "input"})
        assert publish.returncode == 0, publish.stdout + publish.stderr
        identity = state / "run-identity.json"
        original = identity.read_bytes()
        assert invoke("status").returncode == 0
        assert identity.read_bytes() == original
        identity.unlink()
        missing = invoke("status")
        assert missing.returncode != 0 and json.loads(missing.stdout)["state"] == "error"
        assert not identity.exists(), "read-only status created a new run identity"
    print("PASS status preserves existing or missing run identity")


if __name__ == "__main__":
    main()
