"""M0 synthetic evidence from an independent receiver, without provider calls."""
from collections import Counter


def replay(limit, previous, attempts):
    counts = Counter()
    minor_cases = {}
    for index, (slot, phase, axis) in enumerate(attempts):
        if previous + index >= 32 or index >= limit:
            return 'budget', index
        counts[slot] += 1
        if counts[slot] > 1:
            return 'duplicate', index + 1
        if phase in ('critical', 'profile mismatch', 'delivery failed'):
            return phase, index + 1
        if phase == 'minor':
            cases = minor_cases.setdefault((slot[1], axis), set())
            cases.add(slot[0])
            if len(cases) >= 2:
                return 'repeated minor', index + 1
    return 'finished', len(attempts)


slots = [(case, arm) for case in range(8) for arm in range(2)]
clean = [(slot, 'pass', 0) for slot in slots]
checks = [
    ('critical', 0, [(slots[0], 'critical', 0)] + clean[1:], ('critical', 1)),
    ('same-axis minor', 0, [(slots[0], 'minor', 1), clean[1], (slots[2], 'minor', 1)] + clean[3:], ('repeated minor', 3)),
    ('profile drift', 0, [(slots[0], 'profile mismatch', 0)] + clean[1:], ('profile mismatch', 1)),
    ('delivery', 0, [(slots[0], 'delivery failed', 0)] + clean[1:], ('delivery failed', 1)),
    ('duplicate', 0, [clean[0], clean[0]] + clean[1:], ('duplicate', 2)),
    ('round ceiling', 0, clean + [clean[0]], ('budget', 16)),
    ('combined ceiling', 31, clean, ('budget', 1)),
]
for name, previous, attempts, expected in checks:
    actual = replay(16, previous, attempts)
    if actual != expected:
        raise ValueError((name, expected, actual))
    print(name, *actual)
