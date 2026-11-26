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
        self.bridge = self.root / "bridge"
        self.bridge.touch(mode=0o700)
        self.identity = dict(run_id="run", attempt_id="attempt")
        self.plan_data = dict(self.identity, task_id="task", member_id="reviewer",
                              expected_role_version="v1", input_sha256="a" * 64,
                              instruction="Review")
        self.native = dict(status="succeeded", receipt_sha256="c" * 64,
                           turn_evidence={"assignment_id": "task", "turn": {
                               "session": "session", "turn_id": "turn",
                               "completed": True, "usage": {}, "output": "synthetic"}})
        self.scorer = Mock(return_value=7)
        self.observer = self._stub("observe", self.native)
        self.verifier = self._stub("verify_m1", {"action": "accept"})
        self._slot("current")

    def _slot(self, arm):
        self.assignment = f"{arm}/Safe-case_1.0/0"
        slot = self.root / self.assignment
        self.state = slot / "assignment"
        self.state.mkdir(parents=True, exist_ok=True)
        self.ledger = slot / "ledger.jsonl"
        self.lock = slot / "ledger.jsonl.lock"
        self.lock.touch()
        self.plan = self.state / "assignment-v2.plan.json"
        self.plan.write_text(json.dumps(self.plan_data), encoding="utf-8")
        self.start = dict(kind="start", ordinal=1, assignment=self.assignment, run="run",
                          attempt="attempt", thread="session", rpc_id="1",
                          request_sha256="b" * 64)
        self.ack = dict(self.start, kind="ack", turn="turn")

    def _stub(self, name, value):
        patcher = patch.object(m3_score, name, return_value=value)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def _write(self, *rows):
        self.ledger.write_text("".join(json.dumps(row) + "\n" for row in rows),
                               encoding="utf-8")

    def _gate(self, arm="current"):
        return m3_score.score_assignment(arm=arm, assignment=self.assignment,
                                         ledger=self.ledger, state=self.state,
                                         bridge=self.bridge, score=self.scorer)

    def _nonaccept(self, action="hold"):
        result = self._gate()
        self.assertEqual(result["action"], action)
        self.assertNotIn("receipt", result)
        self.assertNotIn("score", result)
        self.scorer.assert_not_called()

    def test_natural_success_same_gate_for_both_arms(self):
        for arm in ("current", "candidate"):
            with self.subTest(arm=arm):
                self._slot(arm)
                self._write(self.start, self.ack)
                self.scorer.reset_mock()
                result = self._gate(arm)
                self.assertEqual(result["action"], "accept")
                self.assertEqual(result["receipt"]["receipt_sha256"], "c" * 64)
                self.assertEqual(result["score"], 7)
                self.assertIs(self.scorer.call_args.args[0], self.native)
                self.scorer.assert_called_once_with(self.native)
                self.observer.assert_called_with(self.bridge, self.state, self.identity,
                                                 self.plan_data)
                self.verifier.assert_called_with([self.native], assignment_id="task",
                                                 member_id="reviewer", role_version="v1")

    def test_matching_optional_native_ids(self):
        self._write(self.start, self.ack)
        self.observer.return_value = dict(self.native, **self.identity)
        self.assertEqual(self._gate()["action"], "accept")

    def test_assignment_cannot_be_relabelled_for_another_arm(self):
        self._write(self.start, self.ack)
        self.assertEqual(self._gate("candidate")["action"], "hold")
        self.observer.assert_not_called()
        self.scorer.assert_not_called()

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
                      dict(self.native, run_id=None),
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

    def test_callback_keeps_the_shared_ledger_lock(self):
        self._write(self.start, self.ack)

        def check_lock(native):
            with self.lock.open("rb+") as writer:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(writer.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return 7

        self.scorer.side_effect = check_lock
        self.assertEqual(self._gate()["score"], 7)
        with self.lock.open("rb+") as writer:
            fcntl.flock(writer.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_callback_errors_are_not_evidence_decisions(self):
        self._write(self.start, self.ack)
        self.scorer.side_effect = BlockingIOError("scorer failure")
        with self.assertRaisesRegex(BlockingIOError, "scorer failure"):
            self._gate()

    def _cli_args(self):
        return ["--arm", "candidate", "--case", "Safe-case_1.0", "--repeat", "0",
                "--root", str(self.root), "--bridge", str(self.bridge)]

    def test_cli_uses_default_plan_and_only_exposes_eligible_reference(self):
        self._slot("candidate")
        for rows, action, status in (
            ((self.start, self.ack), "accept", 0),
            ((self.start,), "hold", 3),
            ((self.start, self.ack, self.start), "reject", 4),
        ):
            with self.subTest(action=action):
                self._write(*rows)
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(m3_score.main(self._cli_args()), status)
                result = json.loads(out.getvalue())
                self.assertEqual(result["action"], action)
                self.assertEqual("receipt" in result, action == "accept")

    def test_cli_rejects_unsafe_slots_and_path_overrides(self):
        args = self._cli_args()
        for option, value in (("--case", "../escape"), ("--repeat", "-1"),
                              ("--repeat", "x"), ("--arm", "other"),
                              ("--assignment", "candidate/other/0"),
                              ("--ledger", "other"), ("--state", "other"), ("--plan", "other")):
            with self.subTest(option=option, value=value):
                invalid = args.copy()
                if option in invalid:
                    invalid[invalid.index(option) + 1] = value
                else:
                    invalid.extend((option, value))
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(m3_score.main(invalid), 2)
                self.assertEqual(json.loads(out.getvalue()),
                                 {"action": "hold", "reason": "invalid_cli_arguments"})
        self.observer.assert_not_called()
