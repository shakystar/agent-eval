# M2 의미 평가·사람 검토 계약

M2는 저장된 증거에 대한 의미 평가, 사람의 판정 검토, 과제 타당성 승인, 기준 사례와의 신뢰성 비교를 추가합니다. M1의 원본·판정 불변성과 기존 실행 소유권을 유지합니다. 원래 과제 실행·조건 주입은 M3 범위입니다.

## 의미 평가

criterion의 rule에 다음 형식을 추가했습니다. kind는 현재 artifact입니다. 실제 행동·상태를 관찰하는 어댑터는 아직 제공하지 않습니다.

```json
{
  "type": "semantic",
  "source": "output",
  "rubric": "복구가 미확인임을 명시하고, 확인 없이 복구 완료라고 단정하지 않는다",
  "needs": ["output", "inputs"]
}
```

채점 입력에는 rubric, 기준 버전·해시, 산출물 해시, 명시한 증거만 포함합니다. 사람 기준 라벨과 평가용 파일을 자동으로 전달하지 않습니다. 필요한 입력이 없으면 모델을 호출하지 않고 unknown으로 기록합니다. 의미 기준이 있는 실험을 기존 `evaluate` 명령으로 실행하면 명시적 judge 선택을 요구하며 중단합니다.

새 채점 응답은 `{verdict, rationale, citations}`입니다. verdict는 met/unmet/unknown/not_applicable이며 citation은 `{source, quote}`입니다. met/unmet에는 최소 한 개의 실제 증거 인용이 필요합니다. 인용이 없는 이진 판정, 존재하지 않는 인용, 잘못된 JSON·필드·판정값은 평가 오류입니다. 인용 검사는 문자열의 실제 존재를 확인하며, 논리적 타당성을 자동 보증하지 않습니다.

요청과 원본 응답, 근거, 오류를 해시로 보존합니다. 저장 응답 평가에서는 Inspect의 scorer/log API로 native Score를 생성하고 unknown과 not_applicable을 구분합니다. 실시간 채점 원장에는 제공자의 응답과 영수증을 보존합니다. 모델의 판정은 항상 draft이며 참조 판정과 일치해도 자동 확정하지 않습니다.

### 채점 실행 경로

- **SavedJudge**: 명시적으로 선택한 response-set을 읽습니다. `{schema_version:1, evaluator, responses}`에서 responses는 요청의 정규 JSON SHA-256→응답 문자열 mapping입니다. 입력·기준이 달라지면 기존 응답을 재사용하지 않습니다. 모델 호출 없이 재평가할 수 있습니다.
- **실제 모델 채점**은 `semantic-grade`로 등록된 의미 기준 ID 또는 비공개 평가 파일 ID를 지정합니다. 호출 전 예산 검사, 평가 잠금, 호출 의도, 항목별 결과, 중단 후 재개는 기존 채점 원장을 사용합니다. 비공개 파일 기준을 선택한 요청은 입력을 `input/<id>`로, 의미 기준을 선택한 요청은 입력을 해당 ID로 인용합니다. 산출물의 출처는 모두 `output`입니다. 의미 기준 ID를 선택하면 `judgment-review`, `reliability --reference`, `report`에서 동일 평가 ID를 사용할 수 있습니다.

evaluator는 `{id, kind, version, model, settings}`입니다. kind는 model 또는 synthetic이며 human으로 위장한 의미 평가기를 허용하지 않습니다. saved 응답의 모델 출처는 제공자의 명시적 선언입니다. 실제 모델 실행 검증에서는 읽기 전용 설정 파일의 모델·reasoning 값과 해시를 별도로 기록했습니다.

## 사람 검토와 기준 사례

`task-review`, `judgment-review`, `reference`는 reviewer/origin/source/created/reason을 요구합니다. origin은 human 또는 synthetic입니다. human 기록은 `--human-attested`를 명시해야 합니다. 이는 입력 제공자의 사람 검토 확인이며 전자서명·신원 인증 서비스는 아닙니다.

| 기록 | 연결 및 동작 |
| --- | --- |
| task-review | bundle id/version/hash, task id/version, approved/rejected/unreviewed 상태를 연결합니다. |
| judgment-review | evaluation ID와 judgment ID에 사람의 verdict를 추가합니다. 원래 모델 판정은 보존합니다. |
| reference | id/version, bundle, calibration/validation split, run·criterion version/hash·output hash별 기준 판정과 근거를 연결합니다. |

검토 수정은 새 ID와 `supersedes`로 현재 head를 명시해야 합니다. 이전 head에서 분기하거나 기존 ID의 내용을 바꾸면 거부합니다. 기준 사례는 새 버전으로 등록하며 중복 run/criterion을 거부합니다. 증거가 없는 이진 기준 판정이나 사람의 이진 확정은 거부합니다.

과제의 원래 validity 필드만으로 승인됐다고 간주하지 않습니다. 정확한 bundle/task 버전에 연결된 사람의 승인 기록이 필요합니다. synthetic 검토는 실제 사람의 판정 확정·과제 승인에 집계하지 않습니다.

보고서에는 원래 잠정 결과와 사람 검토 후 결과를 구분합니다. 승인된 과제에서 명시적으로 확정한 필수 판정만 확정 성공률에 포함합니다. 모든 계획 항목이 검토됐으면 confirmed, 일부만 검토됐으면 partial입니다. 과제 승인 철회 시 성능 결론을 다시 보류하고 기존 이력을 유지합니다. 기준 사례 등록 자체는 모델 판정의 확정을 의미하지 않습니다.

기존 간략 형식의 `human-review`와 `task-review`도 읽습니다. 사람이 직접 내린 판정을 사람 기준에 반영하려면 `--human-attested`로 등록합니다. 출처를 증명할 수 없는 기존 입력은 미확인 상태로 남습니다.

## 신뢰성 지표

`reliability`는 하나의 evaluation을 reference-set 또는 다른 evaluation과 비교합니다. 기준 bundle/version/hash, run·항목·증거 hash가 맞는 경우만 비교합니다. 모델의 원래 초안 판정을 비교하며, 사람이 수정한 판정으로 모델 정확도를 부풀리지 않습니다.

- agreement = 같은 판정 수 / 양쪽 유효 판정 수
- disagreement = 다른 판정 수 / 양쪽 유효 판정 수
- FP rate = FP / (FP+TN), FN rate = FN / (FN+TP)
- coverage = 비교 가능한 항목 수 / 선택한 기준 항목 수

unknown, 평가 오류, 누락, 버전·증거 불일치를 별도 집계합니다. not_applicable은 양쪽 유효 판정 간 일치 비교에는 포함하지만 이진 confusion matrix에서 제외합니다. 분모가 0이면 null과 사유를 반환합니다. reference 없는 경우, synthetic 기준/평가기, 승인되지 않은 과제는 신뢰성 미검증 상태입니다.

사람 기준이 있는 경우에도 상태 `measured_on_human_references`는 선택한 사례에서 측정했다는 뜻입니다. 사례 수·coverage·제외 사유·split을 함께 읽습니다. calibration 결과를 미공개 검증 결과나 일반적인 직무 신뢰성으로 해석하지 않습니다. 서로 다른 evaluator ID는 독립된 식별자라는 정보이며 평가 절차의 완전한 독립성을 증명하지는 않습니다.

## Docker 실행

[M0 빌드](../containers/linux/README.md) 후 저장소 루트에서 실행합니다. M2의 실제 검증 이미지와 source 해시는 [검증 기록](validation/m2.md)에 있습니다.

```sh
docker build -f containers/linux/Dockerfile.m2 -t agent-eval-m2:local .
IMAGE=$(docker image inspect agent-eval-m2:local --format '{{.Id}}')
mkdir -p ../m2-work
WORK=$(realpath ../m2-work)
docker run --rm --network none --mount type=bind,source="$WORK",target=/workspace \
  --entrypoint /opt/inspect-env/bin/python "$IMAGE" -m examples.m2.create_handoff /workspace/input --use-approved-cases

ae() {
  docker run --rm --network none --mount type=bind,source="$WORK",target=/workspace "$IMAGE" "$@"
}
ae --store /workspace/store bundle /workspace/input/bundle.json
ae --store /workspace/store experiment /workspace/input/experiment.json
ae --store /workspace/store import /workspace/input/evidence.json
ae --store /workspace/store task-review /workspace/input/task-review.json --human-attested
ae --store /workspace/store reference /workspace/input/reference.json --human-attested
ae --store /workspace/store semantic-requests m2-calibration --output /workspace/requests.json
```

`--use-approved-cases`는 이 저장소에서 사용자가 승인한 정확한 네 합성 사례를 생성합니다. 다른 과제에 대한 사람 승인을 생성하는 기능이 아닙니다. 옵션을 생략하면 synthetic 출처로 생성합니다. 실제 승인 원문은 [approved-cases.json](../examples/m2/approved-cases.json)에 보존했습니다.

요청 export는 rubric과 출력 원문을 담은 비공개 평가 자료입니다. 공개 보고서와 구분합니다. 평가기가 반환한 response-set을 준비한 뒤 다음 경로로 가져옵니다.

```sh
ae --store /workspace/store semantic-evaluate m2-calibration grade-1 \
  --reviewer operator --reason saved-evaluation --responses /workspace/responses.json
ae --store /workspace/store reliability grade-1 --reference handoff-reference@1 --output /workspace/reliability.json
ae --store /workspace/store report m2-calibration grade-1 --output /workspace/report-1
```

네트워크와 제공자가 준비된 환경에서는 다음 명령으로 장애 인계의 의미 기준을 채점합니다. Codex 어댑터 설정은 [실행 문서](m2-calibration.md)에 있습니다.

```sh
python -m agent_eval --store /workspace/store semantic-grade \
  m2-calibration handoff uncertainty grade-live --model codex-adapter/gpt-6.2-sol
python -m agent_eval --store /workspace/store reliability grade-live --reference handoff-reference@1
```

## 검증

```sh
mkdir -p ../m2-validation
RESULTS=$(realpath ../m2-validation)
docker run --rm --network none --mount type=bind,source="$RESULTS",target=/results \
  --env AGENT_EVAL_IMAGE_ID="$IMAGE" --entrypoint /opt/inspect-env/bin/python \
  "$IMAGE" tests/validate_m2.py --output /results/new-run
```

기본 경로는 M1·M2 회귀 검사와 CLI 검증을 오프라인으로 실행합니다. `--saved-live-root`로 보존된 모델 응답을 읽기 전용 마운트하면 복사본에서 추가 호출 없이 재평가합니다. 전체 검사에 실패 또는 skip이 있으면 검증 명령은 실패합니다.
