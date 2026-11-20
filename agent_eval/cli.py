import argparse
import json
import sys
import sqlite3
from pathlib import Path
from .store import Store
from .contracts import ContractError, PreflightError, canonical, identity
from . import service, semantic
from .report import report, markdown


def export_requests(store, experiment, output):
    _, tasks = service.context(store, experiment)
    packets = []
    for run in store.current_runs():
        if run['experiment'] != experiment:
            continue
        task = tasks[run['task']]
        for criterion in task['criteria']:
            if criterion['rule']['type'] == 'semantic':
                payload, missing = semantic.request(store, run, task, criterion)
                packets.append(dict(request_sha256=identity(payload),
                                    missing_required_evidence=missing, payload=payload))
    with output.open('x', encoding='utf-8') as file:
        file.write(canonical(packets) + '\n')
    return {'requests': len(packets)}


def main():
    parser = argparse.ArgumentParser(description='Local agent execution and evidence evaluation.')
    parser.add_argument('--store', type=Path, required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('bundle','experiment','import'):
        p = commands.add_parser(name)
        p.add_argument('manifest', type=Path)
    p = commands.add_parser('input'); p.add_argument('experiment'); p.add_argument('task')
    p = commands.add_parser('evaluate'); p.add_argument('experiment'); p.add_argument('id')
    p.add_argument('--reviewer',required=True); p.add_argument('--reason',required=True)
    p.add_argument('--parent'); p.add_argument('--bundle',help='Registered id@version for changed criteria')
    p = commands.add_parser('report'); p.add_argument('experiment'); p.add_argument('evaluation')
    p.add_argument('--output',type=Path,required=True)
    p = commands.add_parser('semantic-grade', help='Grade stored outputs with an explicit Inspect model')
    for arg in ('experiment', 'task', 'rubric', 'id'):
        p.add_argument(arg)
    p.add_argument('--model', required=True)
    for name in ('task-review', 'human-review', 'judgment-review', 'reference'):
        p = commands.add_parser(name)
        p.add_argument('manifest', type=Path)
        p.add_argument('--human-attested', action='store_true', help='Attest that a person supplied the judgment')
    p = commands.add_parser('semantic-requests', help='Export private grading requests for offline replay')
    p.add_argument('experiment')
    p.add_argument('--output', type=Path, required=True)
    p = commands.add_parser('semantic-evaluate', help='Grade from responses saved for these exact requests')
    for arg in ('experiment', 'id'):
        p.add_argument(arg)
    p.add_argument('--reviewer', required=True)
    p.add_argument('--reason', required=True)
    p.add_argument('--parent')
    p.add_argument('--responses', type=Path, required=True)
    p = commands.add_parser('semantic-reparse')
    p.add_argument('source'); p.add_argument('id')
    p = commands.add_parser('reliability')
    p.add_argument('evaluation')
    comparison = p.add_mutually_exclusive_group()
    comparison.add_argument('--reference')
    comparison.add_argument('--peer')
    p.add_argument('--output', type=Path)
    for name, help_text in [('execute','Run one planned repetition via role-orchestrator'),
                            ('reconcile','Inspect an existing attempt without submitting work')]:
        p = commands.add_parser(name, help=help_text)
        for key in ('experiment','task','condition'):
            p.add_argument(key)
        p.add_argument('repeat', type=int)
        p.add_argument('--bridge', default='runtime-bridge')
        p.add_argument('--codex', default='codex')
    args = parser.parse_args()
    store = Store(args.store)
    try:
        if args.command in ('bundle','experiment','import'):
            fn = {'bundle':service.register_bundle,'experiment':service.register_experiment,'import':service.import_evidence}[args.command]
            result = fn(store,args.manifest)
        elif args.command in ('execute','reconcile'):
            from .execution import execute
            result = execute(store,args.experiment,args.task,args.condition,args.repeat,args.bridge,args.codex,
                             inspect_only=args.command=='reconcile')
            print(json.dumps(result,ensure_ascii=False))
            return 0 if result['status'] == 'completed' else 1
        elif args.command == 'semantic-grade':
            result = semantic.grade(store, args.experiment, args.task, args.rubric, args.id, args.model)
            if result['counts'].get('scorer_error'):
                print(json.dumps(result))
                return 1
        elif args.command in ('task-review', 'human-review', 'judgment-review', 'reference'):
            from . import review
            register = {'task-review': semantic.review_task, 'human-review': semantic.review,
                        'judgment-review': review.judgment_review, 'reference': review.reference_set}
            record = register[args.command](store, args.manifest, args.human_attested)
            if args.command in ('judgment-review', 'reference'):
                result = {'id': record['id'], 'origin': record['origin']}
            else:
                result = record
        elif args.command == 'semantic-requests':
            result = export_requests(store, args.experiment, args.output)
        elif args.command == 'semantic-evaluate':
            ev = service.evaluate(store, args.experiment, args.id, args.reviewer, args.reason,
                                  args.parent, judge=semantic.SavedJudge(args.responses))
            result = {'id': ev['id'], 'judgments': len(ev['judgments']),
                      'errors': sum(j['processing'] == 'error' for j in ev['judgments'])}
        elif args.command == 'semantic-reparse':
            result = semantic.reparse(store, args.source, args.id)
        elif args.command == 'reliability':
            from .reliability import reliability
            if not args.reference and not args.peer and store.find('semantic', args.evaluation) is not None:
                result = semantic.reliability(store, args.evaluation)
            else:
                result = reliability(store, args.evaluation, args.reference, args.peer)
            if args.output:
                with args.output.open('x', encoding='utf-8') as file:
                    file.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        elif args.command == 'input':
            result = service.execution_input(store,args.experiment,args.task)
        elif args.command == 'evaluate':
            ev = service.evaluate(store,args.experiment,args.id,args.reviewer,args.reason,args.parent,args.bundle)
            result = {'id':ev['id'],'judgments':len(ev['judgments']),'errors':sum(j['processing']=='error' for j in ev['judgments'])}
        else:
            obj = report(store,args.experiment,args.evaluation)
            args.output.mkdir(parents=True,exist_ok=False)
            (args.output/'report.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            (args.output/'report.md').write_text(markdown(obj),encoding='utf-8')
            result = {'report':str(args.output)}
        print(json.dumps(result,ensure_ascii=False,allow_nan=False))
        return 1 if args.command in ('evaluate', 'semantic-evaluate') and result['errors'] else 0
    except PreflightError as exc:
        print(json.dumps({'error':'request_validation', 'execution':'not_started', 'message':str(exc)}),
              file=sys.stderr)
        return 2
    except (ValueError,OSError,sqlite3.Error,KeyError,TypeError) as exc:
        print(json.dumps({'error':type(exc).__name__,'operation':args.command,
                          'message':str(exc) if isinstance(exc,ContractError) else 'Invalid input or local file operation failed.'}),file=sys.stderr)
        return 2
    except ImportError:
        if args.command in ('execute','reconcile'):
            print(json.dumps({'error':'missing_optional_dependency','message':'Use the role-orchestrator environment.'}),file=sys.stderr)
            return 2
        print(json.dumps({'error':'missing_optional_dependency','message':'Install the pinned Inspect adapter environment.'}),file=sys.stderr)
        return 2
    finally:
        store.close()


if __name__ == '__main__':
    raise SystemExit(main())
