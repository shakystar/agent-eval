"""Offline verification with the candidate orchestrator installed. No model dispatch."""
import argparse
import json
from pathlib import Path

from role_orchestrator.assignment import observe
from role_orchestrator.attempts import AttemptReader
from role_orchestrator.role_contracts import digest, role_contract, validate_inputs


HERE = Path(__file__).resolve().parent


def verify(state_root, binary, case_file):
    case = json.loads(case_file.read_bytes())
    assert digest((HERE / 'readonly_identity_regression.py').read_bytes()) == case['test_sha256']
    observations = {}
    for label in ('author', 'reviewer'):
        stage = case[label]
        state = state_root / label
        plan = json.loads((state / 'assignment-v2.plan.json').read_bytes())
        ids = {key: stage[key] for key in ('run_id', 'attempt_id')}
        assert all(plan[key] == value for key, value in ids.items())
        assert plan['revision'] == case['lab_sha'] and plan['backend'] == 'codex'
        assert plan['member_id'] == stage['member_id'] and plan['task_id'] == stage['task_id']
        assert (plan['desired']['model'], plan['desired']['effort']) == (
            stage['requested_model'], stage['requested_effort'])
        pair = AttemptReader(binary, state, ids['run_id']).read(ids['attempt_id'])
        assert pair is not None
        wire, receipt = pair
        assert digest(wire) == stage['wire_sha256'] and digest(receipt) == stage['receipt_sha256']
        message = json.loads(wire)
        inputs = json.loads(message['input'])
        assert digest(message['input'].encode()) == stage['input_sha256']
        assert inputs['base_sha'] == case['base_sha']
        contract = role_contract(plan['member_id'], plan['handoff_id'], 'development-patch-v1')
        validate_inputs(inputs, contract)
        # The live baseline had neither field. Attach the recorded input digest
        # and candidate output contract in memory; preserve the original instruction.
        candidate_plan = {**plan, 'input_sha256': stage['input_sha256'], 'contract': contract}
        checked = observe(binary, state, ids, candidate_plan)
        assert checked['status'] == 'succeeded' and checked['receipt_sha256'] == stage['receipt_sha256']
        artifact = checked['artifact']
        raw = (HERE / stage.get('artifact_file', 'readonly_identity_' +
                                 ('author' if label == 'author' else 'review') + '.json')).read_bytes()
        assert raw == json.loads(receipt)['result']['text'].encode()
        assert digest(raw) == artifact['output_sha256'] == stage['output_sha256']
        assert artifact['payload'] == json.loads(raw)
        if label == 'author':
            assert digest(artifact['payload']['diff'].encode()) == case['patch_sha256']
        else:
            reference = inputs['authored_revision']
            previous = observations['author']
            assert inputs['case_id'] == case['case_id']
            assert inputs['patch_sha256'] == case['patch_sha256'] == artifact['payload']['patch_sha256']
            assert all(reference[key] == previous[key] for key in ('member_id', 'task_id', 'run_id', 'attempt_id'))
            assert reference['artifact'] == previous['payload'] and reference['sha256'] == previous['output_sha256']
            assert inputs['criterion']['id'] == case['criterion_id'] == artifact['payload']['criterion_id']
            assert artifact['payload']['verdict'] == 'accept'
        observations[label] = artifact
    assert observations['author']['member_id'] != observations['reviewer']['member_id']
    assert observations['author']['run_id'] != observations['reviewer']['run_id']
    return {label: {key: item[key] for key in ('attempt_id', 'input_sha256', 'output_sha256',
                                                'contract_sha256', 'receipt_sha256')}
            for label, item in observations.items()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--runtime', required=True)
    parser.add_argument('--case', type=Path, default=HERE / 'readonly_identity_case.json')
    args = parser.parse_args()
    print(json.dumps(verify(args.state, args.runtime, args.case), sort_keys=True))
