#!/bin/sh
# Usage: sh reproduce.sh /path/to/role-orchestrator /new/output-directory
set -eu
source_repo=$(realpath "${1:?source checkout required}")
out=$(realpath -m "${2:?new output directory required}")
evidence=$(dirname "$(realpath "$0")")
image=${IMAGE:-agent-eval-m3:v011-2ac1621}
base=2ac1621890141f69fb2f603467eb1f288bed392f
mkdir -m 700 "$out"
for tree in baseline implementation regression combined; do
    git clone -q --no-hardlinks --no-checkout "$source_repo" "$out/$tree"
    git -C "$out/$tree" checkout -q --detach "$base"
done
git -C "$out/implementation" apply "$evidence/author.patch"
git -C "$out/regression" apply "$evidence/regression.patch"
git -C "$out/combined" apply "$evidence/regression.patch"
git -C "$out/combined" apply "$evidence/author.patch"

run() {
    tree=$1 log=$2 expected=$3
    shift 3
    code=0
    docker run --rm --network none --read-only --cap-drop ALL \
        --security-opt no-new-privileges --pids-limit 128 --memory 1g --cpus 1 \
        --tmpfs /tmp:rw,exec,nosuid,nodev,size=96m -e PYTHONDONTWRITEBYTECODE=1 \
        -e PYTHONPATH=/source -v "$out/$tree:/source:ro" \
        -v "$evidence/strict_json_unicode_check.py:/oracle.py:ro" -w /source \
        --entrypoint /opt/src/role-orchestrator/.venv/bin/python "$image" "$@" \
        >"$out/$log" 2>&1 || code=$?
    test "$code" = "$expected"
}
run baseline baseline.txt 1 /oracle.py /source
run implementation candidate.txt 0 /oracle.py /source
run regression role-baseline.txt 1 -m unittest discover -s tests -p test_strict_json_unicode_scalars.py -v
run combined role-candidate.txt 0 -m unittest discover -s tests -p test_strict_json_unicode_scalars.py -v
grep -Fq 'AssertionError: accepted a lone surrogate:' "$out/baseline.txt"
grep -Fq 'PASS nested lone surrogates' "$out/candidate.txt"
grep -Fq 'FAILED (failures=24)' "$out/role-baseline.txt"
grep -Fxq 'OK' "$out/role-candidate.txt"
