# 실행 ID 조회 결함의 실모델 개발 증거

기준 소스는 `role-orchestrator@6935f81582aa5e1f0e8414cbf4bba31e47089fd9`입니다. 이 버전에서 고정한 검사는 공개 인계 CLI로 정상 상태를 만든 뒤, 실행 ID가 있는 조회와 없는 조회를 각각 호출합니다. 후자에서 새 ID를 쓰는 동작을 모델 배정 전에 재현했습니다. [고정 회귀 검사](readonly_identity_regression.py)

기준 이미지에서 명부의 `acl-007`이 제출한 패치 원문을 추출해 격리 복사본에 그대로 적용했습니다. 기준에서 실패한 같은 검사가 후보에서 통과했습니다. 독립된 `acl-005`에는 작성자의 작업·실행·시도 ID, 산출물 원문 SHA, 패치 SHA와 그 개정을 전달했습니다. 검토 결과의 `accept`는 동일한 패치 SHA를 가리킵니다. 모델과 추론 강도 필드는 배정 당시 요청값입니다. [배정·영수증 해시](readonly_identity_case.json) · [작성 산출물](readonly_identity_author.json) · [검토 결과](readonly_identity_review.json)

후보에서는 새 상태로 단일 `development_case run`을 한 번 호출했습니다. 이 호출이 두 실모델을 차례로 배정해 작성자 개정을 검토자에게 전달했습니다. 별도로 생성된 패치 `91f17a28…`는 독립 검토에서 수락됐으며, 격리한 원본 체크아웃에 적용한 뒤 같은 검사를 통과했습니다. 제품에 반영한 패치는 첫 번째 사례의 `5da1161c…`입니다. 두 번째 사례는 후보 CLI의 실사용 검증입니다. 기준 이미지를 사용하되 Python 모듈은 당시 후보 작업본을 읽기 전용으로 마운트했습니다. 검증 기록에 해당 파일별 지문과 이미지 ID를 보존했습니다. 이후 추가한 명부 사전 점검까지 포함한 코드에서 네트워크를 끄고 원래 상태를 읽기 전용으로 마운트한 뒤, 동일 입력의 `status`와 `run`이 최초 결과와 바이트 단위로 일치함을 확인했습니다. [후보 실행·소스 지문](candidate_case.json) · [후보 작성 산출물](candidate_case_author.json) · [후보 독립 검토](candidate_case_reviewer.json)

## 패치 검증 재현

Linux에서 `ORCHESTRATOR`는 기준 커밋을 가진 로컬 저장소, `EVIDENCE`는 이 문서의 절대 디렉터리, `PYTHON`은 프로젝트 의존성이 설치된 Python 절대 경로입니다. 원본 모델 산출물의 diff 필드를 바이트로 추출합니다.

```bash
set -eu
tmp=$(mktemp -d)
git clone --quiet --no-checkout "$ORCHESTRATOR" "$tmp/tree"
git -C "$tmp/tree" checkout --quiet --detach 6935f81582aa5e1f0e8414cbf4bba31e47089fd9
"$PYTHON" -c 'import hashlib,json,pathlib,sys; d=pathlib.Path(sys.argv[1]); b=json.loads((d/"readonly_identity_author.json").read_bytes())["diff"].encode(); assert hashlib.sha256(b).hexdigest()==json.loads((d/"readonly_identity_case.json").read_bytes())["patch_sha256"]; pathlib.Path(sys.argv[2]).write_bytes(b)' "$EVIDENCE" "$tmp/author.patch"
cd "$tmp/tree"
if "$PYTHON" "$EVIDENCE/readonly_identity_regression.py" > "$tmp/base.log" 2>&1; then exit 1; fi
grep -F 'AssertionError: read-only status created a new run identity' "$tmp/base.log"
git apply --check "$tmp/author.patch"
git apply "$tmp/author.patch"
"$PYTHON" "$EVIDENCE/readonly_identity_regression.py"
```

## 원본 영수증의 오프라인 재판정

같은 네이티브 실행 상태를 보유한 Linux 호스트에서 `STATE`는 작성자·검토자 상태 디렉터리를 포함한 상위 경로이고 `BRIDGE`는 기준 이미지의 실행 파일입니다. 후보 코드가 실제 브리지의 읽기 전용 시도 조회를 사용해 전송·영수증 해시, 역할·작업·입력 결속, 검토 대상 패치와 판정을 다시 확인합니다. 원본 모델 세션·인증 정보는 Git에 저장하지 않습니다. 영수증이 없는 다른 PC에서는 위 패치 회귀만 재현할 수 있습니다.

```bash
PYTHONPATH="$ORCHESTRATOR" "$PYTHON" "$EVIDENCE/verify_development_case.py" \
  --state "$STATE" --runtime "$BRIDGE"
```

두 번째 실행의 원본 상태 디렉터리에는 하위 `author/`와 `reviewer/`가 있습니다. 해당 디렉터리를 `STATE`로 지정하고 위 명령에 `--case "$EVIDENCE/candidate_case.json"`을 추가합니다.
