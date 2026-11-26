import contextlib
import fcntl
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from agent_eval import m3_score


class M3ScoreTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.ledger = self.root / "starts.jsonl"
        self.lock = self.root / "starts.jsonl.lock"
        self.lock.touch()
        self.bridge = self.root / "bridge"
        self.bridge.touch(mode=0o700)
        self.plan = self.root / "pinned.json"
        self.identity = dict(run_id="run", attempt_id="attempt")
        self.plan_data = dict(self.identity, task_id="task", member_id="reviewer",
                              expected_role_version="v1", input_sha256="a" * 64,
                              instruction="Review")
        self.plan.write_text(json.dumps(self.plan_data), encoding="utf-8")
        self.start = dict(kind="start", ordinal=1, assignment="slot", run="run",
                          attempt="attempt", thread="session", rpc_id="1",
                          request_sha256="b" * 64)
        self.ack = dict(self.start, kind="ack", turn="turn")
        self.native = dict(self.identity, status="succeeded", receipt_sha256="c" * 64,
                           turn_evidence={"assignment_id": "task", "turn": {
                               "session": "session", "turn_id": "turn",
                               "completed": True, "usage": {}, "output": "synthetic"}})
        self.scorer = Mock(return_value=7)
        self.observer = self._stub("observe", self.native)
        self.verifier = self._stub("verify_m1", {"action": "accept"})

    def _stub(self, name, value):
        patcher = patch.object(m3_score, name, return_value=value)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def _write(self, *rows):
        self.ledger.write_text("".join(json.dumps(row) + "\n" for row in rows),
                               encoding="utf-8")

    def _gate(self, arm="current"):
        return m3_score.score_assignment(arm=arm, assignment="slot", ledger=self.ledger,
                                         state=self.root, bridge=self.bridge,
                                         plan=self.plan, score=self.scorer)

    def _nonaccept(self, action="hold"):
        result = self._gate()
        self.assertEqual(result["action"], action)
        self.assertNotIn("receipt", result)
        self.assertNotIn("score", result)
        self.scorer.assert_not_called()

    def test_natural_success_same_gate_for_both_arms(self):
        self._write(self.start, self.ack)
        for arm in ("current", "candidate"):
            with self.subTest(arm=arm):
                self.scorer.reset_mock()
                result = self._gate(arm)
                self.assertEqual(result["action"], "accept")
                self.assertEqual(result["receipt"]["receipt_sha256"], "c" * 64)
                self.assertEqual(result["score"], 7)
                self.assertIs(self.scorer.call_args.args[0], self.native)
                self.scorer.assert_called_once_with(self.native)
                self.observer.assert_called_with(self.bridge, self.root, self.identity,
                                                 self.plan_data)
                self.verifier.assert_called_with([self.native], assignment_id="task",
                                                 member_id="reviewer", role_version="v1")

    def test_lost_response(self):
        self._write(self.start)
        self._nonaccept()

    def test_double_start_including_identical_row_or_retry(self):
        for extra in (self.start, dict(self.start, ordinal=2, attempt="retry")):
            with self.subTest(extra=extra):
                self._write(self.start, self.ack, extra)
                self._nonaccept("reject")
        self.observer.assert_not_called()
        self.verifier.assert_not_called()

    def test_missing_invalid_and_mixed_ledger(self):
        self._nonaccept()
        for rows in ((self.ack,), (self.start, dict(self.ack, rpc_id="wrong")),
                     (self.start, self.ack, dict(self.start, assignment="other")),
                     (dict(self.start, ordinal=True), self.ack)):
            with self.subTest(rows=rows):
                self._write(*rows)
                self._nonaccept()
        self.ledger.write_bytes(b'{"kind":"start"}')
        self._nonaccept()

    def test_wrong_native_or_pinned_identity(self):
        self._write(self.start, self.ack)
        for wrong in (dict(self.native, attempt_id="wrong"),
                      dict(self.native, receipt_sha256=None),
                      dict(self.native, turn_evidence=None),
                      dict(self.native, turn_evidence={"assignment_id": "other"}),
                      dict(self.native, turn_evidence={"assignment_id": "task", "turn": {
                          "session": "session", "turn_id": "other"}})):
            with self.subTest(wrong=wrong):
                self.observer.return_value = wrong
                self._nonaccept()
        self.observer.return_value = self.native
        self.plan.write_text(json.dumps(dict(self.plan_data, run_id="wrong")), encoding="utf-8")
        self._nonaccept()

    def test_native_failure_and_uncertain_verdict(self):
        self._write(self.start, self.ack)
        self.verifier.return_value = {"action": "hold"}
        self._nonaccept()
        self.observer.return_value = dict(self.identity, status="failed")
        self.verifier.return_value = {"action": "reject"}
        self._nonaccept("reject")

    def test_lock_contention(self):
        self._write(self.start, self.ack)
        with self.lock.open("rb+") as writer:
            fcntl.flock(writer.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._nonaccept()
        self.observer.assert_not_called()

    def test_cli_uses_default_plan_and_only_exposes_eligible_reference(self):
        self.plan.rename(self.root / "assignment-v2.plan.json")
        args = ["--arm", "candidate", "--assignment", "slot", "--ledger",
                str(self.ledger), "--state", str(self.root), "--bridge", str(self.bridge)]
        for rows, action in (((self.start, self.ack), "accept"), ((self.start,), "hold"),
                             ((self.start, self.ack, self.start), "reject")):
            with self.subTest(action=action):
                self._write(*rows)
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(m3_score.main(args), 0)
                result = json.loads(out.getvalue())
                self.assertEqual(result["action"], action)
                self.assertEqual("receipt" in result, action == "accept")
