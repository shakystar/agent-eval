"""Compare strict_json's handling of Unicode scalar values on a selected checkout."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(sys.argv[1]).resolve()))
from role_orchestrator.contracts import strict_json


def main():
    valid = {
        r'"\ud83d\ude00"': chr(0x1F600),
        '"한글"': "한글",
        r'"\\ud800"': r"\ud800",
    }
    for raw, expected in valid.items():
        if strict_json(raw) != expected:
            raise AssertionError(f"valid Unicode changed: {raw!r}")
    invalid = (
        r'"\ud800"',
        r'{"nested":[{"key":"\udfff"}]}',
        r'[{"\ud800":0}]',
    )
    for raw in invalid:
        try:
            strict_json(raw)
        except ValueError:
            continue
        raise AssertionError(f"accepted a lone surrogate: {raw!r}")
    print("PASS nested lone surrogates rejected; Unicode and literal escapes preserved")


if __name__ == "__main__":
    main()
