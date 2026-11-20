# M1 사용 및 데이터 계약

후속 의미 평가·사람 검토 기능은 [M2 계약](m2-contract.md)에 기록합니다. 아래는 M1의 검증 범위입니다.

M1은 저장된 증거를 등록하고 규칙으로 재평가하는 로컬 도구입니다. 모델·runtime 실행, 의미 평가, 사람의 판정 확정은 포함하지 않습니다.

## 실행 환경

Python 3.12 이상을 사용합니다. 코어는 표준 라이브러리만 사용합니다. 과제/실험 등록, saved-output 가져오기, 기존 판정 보고는 Inspect 없이 가능합니다. Inspect 로그 가져오기와 규칙 채점에는 고정 Inspect 환경이 필요합니다. 의존성은 `pyproject.toml`의 선택적 `inspect` 항목과 M0 환경 파일에 명시했습니다.

기본 검증 경로는 Docker/Linux입니다. [M0 환경](../containers/linux/README.md)을 먼저 빌드한 뒤 저장소 루트에서 실행합니다.

```sh
docker image inspect agent-eval-linux:m0 --format '{{.Id}}'
docker build -f containers/linux/Dockerfile.m1 -t agent-eval-m1:local .
IMAGE=$(docker image inspect agent-eval-m1:local --format '{{.Id}}')
mkdir -p ../m1-work
WORK=$(realpath ../m1-work)
docker run --rm --network none --mount type=bind,source="$WORK",target=/workspace \
  --entrypoint /opt/inspect-env/bin/python "$IMAGE" examples/m1/create_example.py /workspace/input
```

M1 이미지는 코드·테스트·예제 생성기를 포함합니다. source bind mount, 로그인, 인증 파일 없이 동작합니다. 출력 디렉터리는 UID 1000이 쓸 수 있어야 합니다. Dockerfile은 로컬 M0 태그를 사용하므로 빌드 전 base ID를 확인하고 실제 M1 image ID를 기록합니다. 검증한 ID는 [검증 결과](validation/m1/results.json)에 있습니다. 재빌드 결과가 바이트 단위로 같다고 보장하지 않습니다.

```sh
ae() {
  docker run --rm --network none --mount type=bind,source="$WORK",target=/workspace "$IMAGE" "$@"
}
ae --store /workspace/store bundle /workspace/input/bundle.json
ae --store /workspace/store experiment /workspace/input/experiment.json
ae --store /workspace/store import /workspace/input/evidence.json
ae --store /workspace/store input m1-demo decision
ae --store /workspace/store evaluate m1-demo first --reviewer operator --reason initial
ae --store /workspace/store evaluate m1-demo second --reviewer operator --reason regrade --parent first
ae --store /workspace/store report m1-demo second --output /workspace/report-second
```

동일 import는 중복으로 응답합니다. 동일 판정 ID와 기존 보고서 디렉터리는 덮어쓰지 않습니다. 종료 코드는 정상 0, 저장된 채점 오류 포함 1, 계약·파일·의존성 오류 2입니다. 예제는 baseline 3회 중 충족 1·미충족 1·증거 누락 1이며 changed 조건 3회는 미수집입니다. 잠정 계획 성공률은 1/3, 판단 가능한 범위에서는 1/2입니다. 실제 모델 성능 점수가 아닙니다.

## 저장 및 소유권

- `index.sqlite`: 과제/기준 버전, 실험, 증거 인덱스, 실행 연결, 판정 원장을 트랜잭션으로 관리합니다.
- `blobs/<sha256>`: 원본 native 로그, 입력·평가 자료, 출력, 새 채점 로그와 오류 상세를 보존합니다.
- 원본 파일의 바이트 해시와 native 데이터의 의미 해시를 구분합니다. 재직렬화된 같은 Inspect 로그는 기존 실행을 추가하지 않으며 원본 파일별 해시를 보존합니다.
- 동일 native ID의 내용 충돌, 다른 evidence ID로 같은 native 실행을 중복 등록하는 경우, 같은 계획 슬롯에 다른 실행을 연결하는 경우는 거부합니다.
- 한 슬롯은 `(experiment, task, condition, repeat)`입니다. M1은 재시도를 자동 선택하거나 실행하지 않습니다.
- 실패한 인덱스 트랜잭션의 blob이 남을 수 있습니다. 이를 실행·판정에 집계하지 않으며 자동 삭제하지 않습니다. 동시 다중 작성자 및 강제 종료 복구는 이번 검증 범위 밖입니다.

원본 저장소는 비공개 자료를 포함할 수 있습니다. 공개 보고서는 원문·정답·규칙 값·오류 상세·검토 사유를 출력하지 않습니다. 입력 투영은 `inputs`, `allowed_actions`, `outputs`만 사용하며 `evaluation`, 기준, 정답은 전달하지 않습니다. 이는 구조적 분리이며 사용자가 공개 입력 본문에 직접 적은 비밀을 탐지하는 DLP 기능은 아닙니다.

## JSON 계약 v1

실제 예제는 `examples/m1/create_example.py`로 생성합니다. 알 수 없는 필드, 누락, 중복 ID/JSON 키, 비유한 숫자, 지원하지 않는 버전을 거부합니다. 파일 참조는 `{id, path, sha256}`이며 manifest 디렉터리 내부의 실제 파일이어야 합니다. 상위 경로 및 외부를 가리키는 symlink는 거부합니다.

| 객체 | 필드와 의미 |
| --- | --- |
| bundle | schema_version, id, version, split(calibration/validation), family, tasks |
| task | id/version, domain/source, inputs/evaluation 파일 참조, allowed_actions, outputs, completion, criteria, reference_path, validity |
| criterion | id/version, required, kind, rule. 현재 kind=artifact만 지원합니다. 참고 경로는 채점하지 않습니다. |
| experiment | id, hypothesis, bundle의 id/version/정규 JSON sha256, baseline, conditions, repetitions, execution/evaluation budget, varying_fields, comparison_policy |
| condition | id, 실행 adapter/version/소유자/인증 방식 식별, model/name/settings/누락 사유, roles/skills 버전, environment |
| environment | initial_state, reset, isolation, shared_state, session_policy. 계획과 수집값의 차이를 비교 제한으로 표시합니다. |
| evidence manifest | schema_version, id, experiment, format, source 파일 참조, runs 명시적 매핑 |
| run | id, task, condition, repeat, attempt_id, execution_status, environment, started/ended, receipt 식별자, time/tokens/cost 측정값 |
| measurement | value, unit, scope, completeness, missing_reason. null은 사유와 missing 상태가 필수입니다. |
| evaluation | 독립 ID, experiment, parent, reviewer, reason, criterion_bundle, backend, judgments. 기존 판정을 덮어쓰지 않습니다. |

`varying_fields`는 `model.settings.temperature` 같은 condition 경로입니다. 선언하지 않은 조건 차이와 실제 환경 차이는 비교 제한으로 표시합니다. 예산은 M1에서 실험 메타데이터로만 보존하며 실행 통제를 제공하지 않습니다. 입력 자료·완료 조건이 변경되면 새 실험이 필요합니다.

### 두 가지 importer

`format=inspect`: 로컬 native `.eval` 파일의 모든 `(sample_id, epoch)`를 run에 명시적으로 연결합니다. native eval ID·점수·부분 점수·unscored·sample.error·점수 없음·상태·이력·집계를 원본에 보존합니다. 실행 상태는 로그 전체 status로 추정하지 않고 manifest에서 별도로 받습니다. manifest의 실행 사실은 제공자의 선언이며 runtime 영수증 의미 검증은 M3 실행 어댑터 범위입니다.

`format=saved-output-v1`: source는 `{schema_version:1, id, records}`이며 record는 `{id, output, missing_reason}`입니다. output은 파일 참조 또는 null입니다. null에는 누락 사유가 필요합니다. record ID는 run ID에 대응하며 전체 record를 매핑해야 합니다.

로그 안의 task_file, scorer 이름, provider 설정을 실행하지 않습니다. Inspect `read_eval_log`로 읽고, 채점할 때에는 출력만 담은 새 로그와 명시적 내장 scorer, `mockllm/model`을 사용합니다. 이는 임의 사용자 코드를 실행하는 플러그인 API가 아닙니다.

### 규칙과 재평가

지원 규칙은 출력의 `nonempty`, `contains(value)`, `json_equals(pointer,value)`입니다. JSON pointer는 `/decision` 형태입니다. 잘못된 제출 JSON은 미충족, 출력 누락은 판단 불가, scorer 예외는 평가 오류입니다. 미지원 action/state 기준이나 규칙은 등록 시 거부합니다.

기준을 변경하려면 bundle·task·criterion 버전을 갱신하여 등록하고 `evaluate ... --bundle id@version --parent 이전판정ID`로 실행합니다. 같은 기준 버전의 내용 변경, 재평가 중 입력/완료 조건 변경은 거부합니다. 각 판정에 기준·backend 버전, 출력 해시, 새 native 채점 로그를 연결합니다. `reviewer/reason/parent`는 재평가 원장 정보이며 사람이 결과를 확정했다는 의미가 아닙니다.

### 보고

JSON과 Markdown을 함께 생성합니다. 계획 반복 수, 과제·반복별 상태, 누락·평가 오류, native 집계, 측정 누락률, 조건 차이를 표시합니다. source와 판정 blob의 해시를 재확인합니다. 각 조건을 같은 평가 버전으로 채점하므로 기준이 다른 결과를 직접 비교하지 않습니다.

M1 판정은 모두 draft입니다. 잠정 충족률은 별도 필드에 두고 확정 성공 건수는 0으로 유지하며, 과제 타당성·사람 기준 검증 전 성능 결론은 보류합니다. 원본 native accuracy와 계획 반복 전체의 성공률은 서로 다른 지표입니다. 시간·토큰·비용 null은 0으로 대체하지 않습니다.

## 검증 명령

```sh
mkdir -p ../m1-validation
RESULTS=$(realpath ../m1-validation)
docker run --rm --network none --mount type=bind,source="$RESULTS",target=/results \
  --env AGENT_EVAL_IMAGE_ID="$IMAGE" --entrypoint /opt/inspect-env/bin/python \
  "$IMAGE" tests/validate_m1.py --output /results/new-run
```

실패나 skip이 있으면 검증 명령이 실패합니다. `--live-log`는 선택적으로 이미 저장된 M0 로그를 추가 확인하며 새 모델 작업을 실행하지 않습니다. 검증 결과와 source 해시는 자동 저장합니다. Windows에서 코어만 확인할 때는 `python -m unittest discover -s tests -v`를 사용하며 Inspect 미설치 skip은 전체 M1 통과로 간주하지 않습니다.
