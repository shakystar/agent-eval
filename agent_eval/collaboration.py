"""Offline metrics for the bounded writer-to-reviewer workflow."""
from collections import Counter

from .contracts import digest, loads, rate, require


def received_document(store, execution):
    """Use only the document in the first reviewer's acknowledged request."""
    stages = {stage['stage']: stage for stage in execution['stages']}
    writer = stages.get('write', {})
    review = stages.get('review', {})
    if review.get('status') != 'completed' or not all(review.get(key) for key in (
        'input_sha256', 'wire_sha256', 'receipt_sha256',
    )):
        return None
    sent = store.read_blob(review['input_sha256']).decode()
    wire = loads(store.read_blob(review['wire_sha256']))
    receipt = loads(store.read_blob(review['receipt_sha256']))
    require(wire['run_id'] == execution['runtime_run'] and wire['attempt_id'] == review['attempt_id'] and wire['id'] == 'review'
            and wire['role'] == 'reviewer' and receipt['task']['id'] == 'review'
            and receipt['task']['role'] == 'reviewer' and receipt['status'] == 'succeeded'
            and wire['input'] == sent == receipt['task']['input'], 'review delivery evidence mismatch')
    doc = loads(sent).get('document')
    if doc is None or not writer.get('output_sha256'):
        return None
    require(isinstance(doc, dict) and isinstance(doc.get('text'), str)
            and digest(doc['text'].encode()) == doc.get('sha256') == writer['output_sha256'],
            'handoff document mismatch')
    return doc['text']


def handoff_observation(required, scenario, document):
    if scenario != 'collaboration':
        return {'items': {}, 'reason': 'not_collaboration'}
    if not required:
        return {'items': {}, 'reason': 'no_required_handoff_items'}
    if document is None:
        return {'items': {item['id']: 'unknown' for item in required}, 'reason': 'missing_handoff_evidence'}
    items = {item['id']: 'delivered' if item['contains'] in document else 'absent' for item in required}
    return {'items': items, 'reason': None}


def recovery_observation(plan, workflow):
    fault = next((i for i in plan.get('injections', []) if i['kind'] == 'tool_failure'), None)
    if fault is None:
        return 'no_fault_planned'
    observations = workflow['injections'] if workflow else []
    observed = next((i for i in observations if i['id'] == fault['id']), None)
    if observed is None:
        return 'missing_injection_evidence'
    if observed['status'] == 'not_applied':
        reason = observed.get('reason')
        return reason if reason in ('stage_not_reached', 'model_not_started') else 'not_applied'
    if observed['status'] == 'uncertain':
        return 'application_uncertain'
    require(observed['status'] == 'applied' and observed['count'] == 1
            and observed['kind'] == 'tool_failure' and observed['stage'] == fault['stage']
            and observed['tool'] == fault['tool'], 'fault observation mismatch')
    recovery = observed.get('recovery')
    return recovery if recovery in ('read_succeeded', 'read_failed') else 'recovery_unobserved'


def condition_metrics(rows):
    handoff_reasons = Counter()
    delivered = planned = unknown = 0
    recovery = Counter()
    for row in rows:
        handoff = row['handoff']
        items = Counter(handoff['items'].values())
        delivered += items['delivered']
        planned += sum(items.values())
        unknown += items['unknown']
        if handoff['reason']:
            handoff_reasons[handoff['reason']] += len(handoff['items']) or 1
        if items['absent']:
            handoff_reasons['item_absent'] += items['absent']
        recovery[row['fault_recovery']] += 1
    handoff_rate = rate(delivered, planned)
    if planned and planned == unknown:
        handoff_rate.update(value=None, missing_reason='missing_handoff_evidence')
    handoff_rate['reason_counts'] = dict(handoff_reasons)
    handoff_rate['excluded_slots'] = {reason: handoff_reasons[reason] for reason in
                                     ('not_collaboration', 'no_required_handoff_items') if handoff_reasons[reason]}
    successes = recovery.pop('read_succeeded', 0)
    applied = successes + recovery['read_failed'] + recovery['recovery_unobserved']
    recovery_rate = rate(successes, applied)
    if applied and recovery['recovery_unobserved'] == applied:
        recovery_rate.update(value=None, missing_reason='recovery_unobserved')
    recovery_rate['reason_counts'] = dict(recovery)
    recovery_rate['excluded_slots'] = {reason: count for reason, count in recovery.items()
                                      if reason not in ('read_failed', 'recovery_unobserved')}
    return {'required_handoff_rate': handoff_rate, 'recovery_success_rate': recovery_rate}
