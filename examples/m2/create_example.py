"""Create synthetic calibration material for a maintenance notice."""
from pathlib import Path
import argparse

from examples.m1 import create_example as fixture
from agent_eval.contracts import digest, identity, load


def make(root):
    bundle, experiment, evidence = fixture.make(root)
    task = bundle['tasks'][0]
    task.update(id='notice', source='Synthetic maintenance schedule', domain='customer communication',
                inputs=[fixture.ref(root, 'brief.txt', 'Write a notice. Checkout is unavailable 14:00–15:00 UTC. '
                                    'Browsing remains available. Customers can retry checkout after 15:00 UTC.')],
                evaluation=[fixture.ref(root, 'rubric.txt', 'The notice must convey the checkout outage window '
                                        'and timezone, continued browsing, and when to retry. Accept paraphrases. '
                                        'Fail contradictory claims.')],
                outputs=['customer notice'], completion='Accurately communicate service impact and recovery.',
                criteria=[dict(id='has-notice', version='1', required=True, kind='artifact',
                               rule=dict(type='nonempty', source='output'))])
    bundle.update(id='notice-calibration', family='maintenance-notice')
    experiment.update(id='notice-demo', bundle=dict(id=bundle['id'], version='1', sha256=identity(bundle)))
    evidence.update(experiment=experiment['id'])
    source = load(root/'source.json')
    for run in evidence['runs']:
        run['task'] = 'notice'
    for record, text in zip(source['records'], [
        'Browse as usual. Checkout pauses from 14:00 to 15:00 UTC. Please try paying again after 15:00 UTC.',
        'All services will be unavailable until further notice.'
    ]):
        record['output'] = fixture.ref(root, record['output']['path'], text)
    fixture.write(root, 'source.json', source)
    evidence['source']['sha256'] = digest((root/'source.json').read_bytes())
    for name, obj in [('bundle', bundle), ('experiment', experiment), ('evidence', evidence)]:
        fixture.write(root, name+'.json', obj)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    make(parser.parse_args().directory)
