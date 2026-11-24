"""External witness. Invoke the actual native subprocesses and stop only at named boundaries."""
import json, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from role_orchestrator import planning_team as broker
mode=sys.argv.pop(1)
witness=Path(sys.argv.pop(1)).absolute()
def record(event,task=None):
    with witness.open('a') as out:
        out.write(json.dumps({'event':event,'task':task,'pid':os.getpid()})+'\n')
        out.flush();os.fsync(out.fileno())
native=broker.native
invoke=broker.invoke
def observed(args,current,dispatch,**kwargs):
    if dispatch and mode=='stop-before':
        record('intent-persisted',current['task_id'])
        os._exit(71)
    value=native(args,current,dispatch,**kwargs)
    if dispatch and mode=='stop-after':
        assert value['value']['verdict']['status']=='succeeded'
        record('native-succeeded-before-team-checkpoint',current['task_id'])
        os._exit(72)
    return value
def counted(cmd,data,**kwargs):
    if cmd[0]=='role_orchestrator.assignment' and '--task' in cmd:
        record('native-dispatch',cmd[cmd.index('--task')+1])
    return invoke(cmd,data,**kwargs)
broker.native=observed
broker.invoke=counted
record('started')
broker.main()
