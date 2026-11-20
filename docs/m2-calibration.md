# M2 점검 공지문 보정 예제

저장소 루트에서 `docker build -f containers/linux/Dockerfile.m2 -t agent-eval-m2:dev .`로 빌드합니다. 컨테이너의 /opt/agent-eval-m2에서 /opt/inspect-env/bin/python을 사용합니다.
다음 명령은 합성 공지문 두 건과 출력 누락 한 건을 등록합니다.

```sh
ae() { /opt/inspect-env/bin/python -m agent_eval --store /workspace/store "$@"; }
/opt/inspect-env/bin/python -m examples.m2.create_example /workspace/notice
ae bundle /workspace/notice/bundle.json
ae experiment /workspace/notice/experiment.json
ae import /workspace/notice/evidence.json
```

실제 채점에서는 선택한 Inspect 제공자의 모델 이름을 MODEL에 지정합니다. 다음 명령은 해당 모델에 과제 입력, 평가 기준, 저장된 공지문을 전송합니다. 평가 ID마다 한 번 실행합니다.

```sh
ae semantic-grade notice-demo notice rubric.txt grade-1 --model "$MODEL"
ae reliability grade-1
```

검토자는 brief.txt, rubric.txt와 각 산출물을 읽고 독립적으로 판정합니다.
누락된 산출물은 unknown으로 기록할 수 있습니다. 아래 필드에 실제 값을 작성한 후 파일을 등록합니다.

- `ae human-review review.json`은 evaluation, run, reviewer, reason, verdict를 받습니다. verdict는 met, unmet, unknown 중 하나입니다.
- `ae task-review validity.json`은 bundle(이 예제에서는 notice-calibration@1), task(notice), reviewer, reason, validity(approved 또는 rejected)를 받습니다.
- `ae reliability grade-1`은 판정 가능한 쌍의 수, 일치·불일치, 오탐·미탐, 기준 누락과 판정 불가 건수를 출력합니다. 비교 가능한 쌍이 없으면 unverified입니다.

원본 채점 응답과 근거는 로컬 store에 보관합니다. 한 평가·실행 쌍에는 사람 기준 하나를 등록합니다. 이 예제의 과제 타당성과 사람 기준은 미확정입니다.

## 실제 모델 검증 결과

Qwen2.5-1.5B-Instruct Q4_K_M으로 A와 B를 채점했습니다. 원본 응답의 Markdown JSON 코드 블록 처리 오류를 수정하고 `semantic-reparse notice-v1-live notice-v1-reparsed`로 저장 응답을 다시 읽었습니다. 모델을 다시 호출하지 않았습니다.

사람 기준과 비교 가능한 두 건에서 일치는 1건입니다. A의 “Browse as usual”을 모델이 탐색 가능 안내로 인정하지 않아 미탐이 발생했습니다. B에 대한 미충족 판정은 일치했습니다. C는 사용자 기준으로 미충족이지만 저장 로그에 출력이 없고 실행 상태가 불확실해 비교에서 제외했습니다. 이 결과는 Qwen 채점 경로의 기본 공지문 보정 기록입니다. [사례별 원본 응답과 지표](validation/m2/results.json)

## Codex 어댑터 채점

Codex에 로그인된 호스트에서 Go 1.26 이상으로 채점기를 빌드합니다. Go 모듈과 체크섬은 adapters/codex에 고정되어 있습니다. 저장소 루트에서 실행합니다.

```sh
mkdir -p artifacts/bin
(cd adapters/codex && go build -o ../../artifacts/bin/codex-grader .)
export AGENT_EVAL_CODEX_GRADER="$PWD/artifacts/bin/codex-grader"
python3.12 -m agent_eval --store artifacts/m2-local/store semantic-grade \
  notice-demo notice rubric.txt notice-sol-new --model codex-adapter/gpt-6.2-sol
```

공지문 예제가 등록된 store와 새 평가 ID를 사용합니다. 각 산출물은 별도 advisory 세션에서 평가합니다. 로그인은 설치된 Codex가 관리하고 모델 호출은 원격에서 수행합니다. 원본 응답·세션 ID·사용량은 로컬 store에 기록합니다.

동일한 A·B 산출물에서 Sol은 사람 판정과 2/2 일치했습니다. C는 원본 출력 누락으로 모델 호출과 이진 비교에서 제외했습니다. [사례별 결과 및 사용량](validation/m2/codex-sol.json)

## 실패 상태와 재개

`semantic-grade`는 평가와 입력 목록을 예약하고 호출 직전 의도와 항목별 결과를 별도 트랜잭션으로 저장합니다. 중단된 평가에 같은 인자로 같은 ID를 지정하면 완료 항목은 재사용하고, 호출 의도만 남은 항목은 `interrupted_call / unknown`으로 기록합니다. 남은 미호출 항목부터 진행합니다. 완료된 평가 ID는 중복 실행을 거부합니다.

CLI와 신뢰성 보고의 실패 항목에서 `dispatch`는 제공자 호출 실패, `response_format`은 받은 응답의 판독 실패입니다. Codex의 구조화된 실패는 stage, code, execution, retryable, attempts를 보존합니다. retryable은 재시도 적격성입니다. 채점기는 실패한 항목을 자동 재전송하지 않습니다. 현재 두 제공자는 강제 평가 예산을 보장할 수 없어 enforced 실험을 호출 전에 거부합니다.

사람 기준은 같은 실험·과제·루브릭·실행·산출물을 공유하는 평가와 재파싱에 재사용합니다. 같은 항목에 정정 판정과 사유를 등록하면 이전 판정을 보존하고 최신 기준으로 보고합니다. 기존 저장소의 평가별 기준도 읽습니다. 서로 충돌하는 기존 판정은 새 평가에 자동 승계하지 않습니다.
