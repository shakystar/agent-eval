#!/usr/bin/env python3
"""Offline M5 approval evidence verifier (Python 3.11+, POSIX)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

EXPECTED = {
    'first': ('completed', 1), 'repeat': ('completed', 0),
    'concurrent': ('completed', 1), 'interrupted': ('uncertain', 0),
    'recover': ('completed', 0), 'stale': ('conflict', 0),
    'unsupported': ('unsupported', 0),
}
STATUSES = {status for status, _ in EXPECTED.values()}
REPOS = {'role-runtime', 'role-orchestrator', 'codex-adapter', 'agent-eval'}
EXIT = {'passed': 0, 'failed': 1, 'invalid': 2, 'incomplete': 3, 'unmeasured': 3}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def sha(value, pattern, label):
    require(isinstance(value, str) and re.fullmatch(pattern, value), f'{label}: invalid SHA')
    return value.lower()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f'duplicate JSON key: {key!r}')
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError(f'invalid JSON constant: {value}')


def read_json(stream):
    return json.load(stream, object_pairs_hook=unique_object, parse_constant=reject_constant)


def read_ref(root, name, reader):
    require(nonempty(name) and '\x00' not in name, 'invalid evidence reference')
    parts = name.split('/')
    require(all(part not in ('', '.', '..') for part in parts), f'unsafe reference: {name!r}')
    directory = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(root, directory)
    try:
        for part in parts[:-1]:
            child = os.open(part, directory, dir_fd=fd)
            os.close(fd)
            fd = child
        file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            require(stat.S_ISREG(os.fstat(file_fd).st_mode), f'not a regular file: {name!r}')
            with os.fdopen(file_fd, 'rb', closefd=False) as stream:
                return reader(stream)
        finally:
            os.close(file_fd)
    finally:
        os.close(fd)


def attempt_set(row, key):
    values = row[key]
    require(isinstance(values, list) and all(map(nonempty, values)), f'{key}: expected native ID list')
    ids = set(values)
    require(len(ids) == len(values), f'{key}: duplicate attempt ID')
    return ids


def check_cases(rows, root):
    require(isinstance(rows, list), 'cases must be an array')
    results, hashes_by_run = {}, {}
    for row in rows:
        require(isinstance(row, dict), 'case must be an object')
        case_id, run_id, status = row['id'], row['run_id'], row['observed_status']
        require(isinstance(case_id, str) and case_id in EXPECTED and case_id not in results,
                'unknown or duplicate case ID')
        require(nonempty(run_id), f'{case_id}: invalid run_id')
        require(isinstance(status, str) and status in STATUSES, f'{case_id}: invalid observed_status')
        review_sha = sha(row['review_sha256'], r'[0-9a-fA-F]{64}', f'{case_id}.review_sha256')
        before, after = (attempt_set(row, key) for key in ('attempts_before', 'attempts_after'))
        added, removed = sorted(after - before), sorted(before - after)
        expected_status, expected_count = EXPECTED[case_id]
        errors = []
        if status != expected_status:
            errors.append('status_mismatch')
        if len(added) != expected_count:
            errors.append('dispatch_count_mismatch')
        if removed:
            errors.append('attempt_ids_removed')
        artifact, name = row['artifact'], row.get('artifact_file')
        digest, actual, missing = None, None, False
        if artifact is not None:
            require(isinstance(artifact, dict) and nonempty(artifact.get('id')), f'{case_id}: invalid artifact')
            digest = sha(artifact['sha256'], r'[0-9a-fA-F]{64}', f'{case_id}.artifact.sha256')
            hashes_by_run.setdefault(run_id, {}).setdefault(digest, []).append(case_id)
        if status == 'completed':
            require(digest is not None and nonempty(name), f'{case_id}: completed requires artifact and artifact_file')
        if name is not None:
            require(digest is not None, f'{case_id}: artifact_file requires artifact metadata')
            try:
                actual = read_ref(root, name, lambda stream: hashlib.file_digest(stream, 'sha256').hexdigest())
            except FileNotFoundError:
                missing = True
            if actual is not None and actual != digest:
                errors.append('artifact_hash_mismatch')
        results[case_id] = dict(run_id=run_id, review_sha256=review_sha, observed_status=status,
                                expected_status=expected_status, expected_new_dispatches=expected_count,
                                new_dispatches=len(added), new_attempt_ids=added, removed_attempt_ids=removed,
                                artifact_id=artifact['id'] if artifact is not None else None,
                                artifact_file=name, artifact_sha256=digest, actual_sha256=actual,
                                artifact_missing=missing, errors=errors)
    for groups in hashes_by_run.values():
        if len(groups) > 1:
            for case_ids in groups.values():
                for case_id in case_ids:
                    results[case_id]['errors'].append('contradictory_artifact_hash_for_run')
    for result in results.values():
        result['status'] = ('failed' if result['errors'] else
                            'incomplete' if result['artifact_missing'] else 'passed')
    return {case_id: results.get(case_id, {'status': 'unmeasured'}) for case_id in EXPECTED}


def check_legacy(record, root):
    require(isinstance(record, dict), 'legacy entry must be an object')
    claims = {key: record[key] for key in ('expected', 'completed')}
    require(all(value is None or (type(value) is int and value >= 0) for value in claims.values()),
            'legacy counts must be nonnegative integers or null')
    source = record['source']
    result = dict(source=source, declared_counts=claims, status='unmeasured')
    if source is not None:
        try:
            records = read_ref(root, source, read_json)
            require(isinstance(records, dict) or
                    (isinstance(records, list) and all(isinstance(item, dict) for item in records)),
                    'legacy source must contain a JSON object or an array of objects')
            result.update(status='unverified', reason='no supplied M3 driver record format')
        except FileNotFoundError:
            result.update(status='incomplete', reason='source file not found')
        except (OSError, ValueError, RecursionError) as exc:
            result.update(status='invalid', reason=str(exc))
    return result


def verify(doc, root, report):
    require(isinstance(doc, dict) and type(doc.get('version')) is int and doc['version'] == 1,
            'expected evidence schema version 1')
    for label in ('baseline', 'candidate'):
        revisions = doc[label]
        require(isinstance(revisions, dict) and revisions.keys() == REPOS, f'{label}: invalid repository keys')
        report[label] = {key: sha(revisions[key], r'(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})',
                                  f'{label}.{key}') for key in sorted(REPOS)}
    cases = check_cases(doc['cases'], root)
    states = {row['status'] for row in cases.values()}
    acceptance = ('failed' if 'failed' in states else 'unmeasured' if states == {'unmeasured'} else
                  'incomplete' if states != {'passed'} else 'passed')
    report['acceptance'] = dict(status=acceptance, cases=cases)
    legacy = doc['legacy']
    require(isinstance(legacy, dict), 'legacy must be an object')
    regression = {kind: check_legacy(legacy[kind], root) for kind in ('fixture', 'live')}
    report['legacy_regression'] = regression
    report['status'] = 'invalid' if any(row['status'] == 'invalid' for row in regression.values()) else acceptance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', type=Path)
    parser.add_argument('--output', type=Path, help='new JSON report path; default: stdout')
    args = parser.parse_args()
    report = dict(version=1, evidence_file=str(args.evidence.absolute()),
                  report_file=str(args.output.absolute()) if args.output is not None else None)
    try:
        path = args.evidence.resolve(strict=True)
        report['evidence_dir'] = str(path.parent)
        require(path.is_file(), 'evidence input must be a regular file')
        with path.open('rb') as stream:
            verify(read_json(stream), path.parent, report)
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        report.update(status='invalid', error=str(exc))
    payload = json.dumps(report, ensure_ascii=True, indent=2) + '\n'
    try:
        if args.output is None:
            sys.stdout.write(payload)
        else:
            with args.output.open('x', encoding='utf-8') as stream:
                stream.write(payload)
    except OSError as exc:
        print(f'cannot write report: {exc}', file=sys.stderr)
        return 2
    return EXIT[report['status']]


if __name__ == '__main__':
    sys.exit(main())
