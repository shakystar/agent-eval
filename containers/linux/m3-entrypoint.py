"""Select the dependency environment for the requested agent-eval command."""
import argparse
import os
import sys

parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
parser.add_argument('--store')
parser.add_argument('command', nargs='?')
options, _ = parser.parse_known_args()
python = ('/opt/src/role-orchestrator/.venv/bin/python' if options.command in ('execute', 'reconcile')
          else '/opt/inspect-env/bin/python')
os.execv(python, [python, '-m', 'agent_eval', *sys.argv[1:]])
