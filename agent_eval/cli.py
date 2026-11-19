import argparse
import json
import sys
from pathlib import Path
from .store import Store
from .contracts import ContractError
from . import service
from .report import report, markdown


def main():
    parser = argparse.ArgumentParser(description='Local evidence-only evaluation; never executes an agent.')
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
    args = parser.parse_args()
    store = Store(args.store)
    try:
        if args.command in ('bundle','experiment','import'):
            fn = {'bundle':service.register_bundle,'experiment':service.register_experiment,'import':service.import_evidence}[args.command]
            result = fn(store,args.manifest)
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
        return 1 if args.command=='evaluate' and result['errors'] else 0
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print(json.dumps({'error':type(exc).__name__,'operation':args.command,
                          'message':str(exc) if isinstance(exc,ContractError) else 'Invalid input or local file operation failed.'}),file=sys.stderr)
        return 2
    except ImportError:
        print(json.dumps({'error':'missing_optional_dependency','message':'Install the pinned Inspect adapter environment.'}),file=sys.stderr)
        return 2
    finally:
        store.close()


if __name__ == '__main__':
    raise SystemExit(main())
