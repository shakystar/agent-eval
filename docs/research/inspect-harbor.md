# Inspect AI·Harbor 비교와 재사용 결정

- 결정일: 2026-11-20
- 상태: 기획 결정입니다. 설치·통합·성능 검증은 수행하지 않았습니다.
- 적용 명세: [기획 명세 v0.2](../planning-spec.md)
- 확인한 소스: Inspect AI `ec5d110b1704a6eb31e2efedec59a12190df80e1`, Harbor `a215bfa03ccc026d22a0f11d5d6c51a8a46f0510`
- 자료 범위: 고정 커밋의 계약·문서·일부 구현과 공식 온라인 문서입니다. 온라인 문서는 위 커밋과 동일 배포본임을 보장하지 않으므로 채택할 버전의 호환성 검사에서 다시 대조합니다.

## 1. 결정

**Inspect AI의 채점·재평가·로그 API·뷰어를 첫 재사용 대상으로 선택합니다. Harbor는 컨테이너와 실행 환경이 필요한 과제의 후속 실행 백엔드로 선택합니다. agent-eval은 실험 조건, 협업·주입 계약, 증거 연결, 판정 확정과 비교 정책을 직접 개발합니다.**

기존 role-orchestrator → role-runtime → codex-adapter 경로는 첫 실제 실행 대상으로 유지합니다. Inspect의 모델 라우터나 Harbor의 Codex 실행기로 자동 교체하지 않습니다. 두 도구를 동시에 필수 의존성으로 설치하지 않습니다.

이는 기능과 계약의 적합성에 따른 선택입니다. 성능 우위나 즉시 호환됨을 확인한 결정은 아닙니다. M0 계약 검증을 통과한 경로만 구현에 사용하고, 통과하지 못하면 불일치와 수정 비용을 기록해 이 결정을 갱신합니다. 검증 실패를 이유로 범용 실행기 전체를 바로 자체 구현하지 않습니다.

## 2. 상세 비교

| 관점 | Inspect AI | Harbor | 결정과 근거 |
| --- | --- | --- | --- |
| 중심 단위 | Dataset의 Sample, Task, Solver/Agent, Scorer로 평가를 구성합니다. | Task의 지시문·환경·검증기를 Trial로 실행하고 Job으로 묶습니다. | 문서·저장 증거 평가에는 Inspect, 환경 조작 과제에는 Harbor를 연결합니다. [I-02](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec5d110b1704a6eb31e2efedec59a12190df80e1/docs/scoring-workflow.qmd) · [H-01](https://github.com/harbor-framework/harbor/blob/a215bfa03ccc026d22a0f11d5d6c51a8a46f0510/src/harbor/models/job/config.py) · [H-03](https://github.com/harbor-framework/harbor/blob/a215bfa03ccc026d22a0f11d5d6c51a8a46f0510/src/harbor/models/task/config.py) · [B-01](https://meridianlabs-ai.github.io/inspect_harbor/tasks.html) |
| 기존 에이전트 연결 | Python/Sandbox Bridge가 모델 호출을 Inspect provider로 라우팅합니다. 외부 프로그램 호출은 별도 solver로 구성할 수 있습니다. | 설치형 에이전트와 환경 실행 계약이 있습니다. Codex 구현에는 API 키와 auth.json 경로가 있습니다. | 현재 app-server·영수증·세션 계약과 동등하다고 보지 않습니다. 첫 경로는 기존 실행 결과를 가져오는 평가 어댑터입니다. [I-01](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec5d110b1704a6eb31e2efedec59a12190df80e1/docs/agent-bridge.qmd) · [H-07](https://github.com/harbor-framework/harbor/blob/a215bfa03ccc026d22a0f11d5d6c51a8a46f0510/src/harbor/agents/installed/codex.py) · [R-01](https://github.com/shakystar/codex-adapter/blob/main/README.md) |
| 다중 역할 | handoff와 입력·출력 필터를 제공합니다. | ATIF에 하위 에이전트 기록과 식별자가 있습니다. multi-step은 공유 환경의 순차 과제입니다. | handoff나 하위 기록을 팀 성과의 정답으로 취급하지 않습니다. 역할별 입력과 필수 인계 기준은 직접 정의합니다. [I-07](https://inspect.aisi.org.uk/multi-agent.html) · [H-04](https://github.com/harbor-framework/harbor/blob/a215bfa03ccc026d22a0f11d5d6c51a8a46f0510/src/harbor/models/trajectories/trajectory.py) · [H-08](https://www.harborframework.com/docs/tasks/multi-step) |
| 조건 주입 | 사람의 개입과 메시지 기록을 지원하며 지원 scaffold가 필요합니다. | 단계별 준비 hook과 자료 업로드를 지원합니다. | 임의 도구 장애·변경 요구·적용 영수증까지 보장하는 공통 주입기는 확인하지 못했습니다. 주입 계획과 실제 실행 지점 계약은 직접 개발합니다. [I-08](https://inspect.aisi.org.uk/intervention.html) · [H-08](https://www.harborframework.com/docs/tasks/multi-step) |
| 재채점 | 생성 없이 저장 로그를 채점하며 추가 또는 덮어쓰기를 선택합니다. | 보관한 산출물과 새 separate verifier로 에이전트를 다시 실행하지 않고 regrade합니다. | 두 기능 모두 재사용합니다. 첫 버전은 Inspect를 사용하고 Harbor 재채점은 환경 어댑터 도입 시 연결합니다. 원본 덮어쓰기는 사용하지 않습니다. [I-02](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec5d110b1704a6eb31e2efedec59a12190df80e1/docs/scoring-workflow.qmd) · [H-05](https://github.com/harbor-framework/harbor/blob/a215bfa03ccc026d22a0f11d5d6c51a8a46f0510/docs-mintlify/jobs/regrade.mdx) · [H-06](https://github.com/harbor-framework/harbor/blob/a215bfa03ccc026d22a0f11d5d6c51a8a46f0510/src/harbor/trial/regrade.py) |
| 판정 오류 | Score의 reason·explanation·metadata·history와 unscored를 제공합니다. 채점 오류는 sample error로 남습니다. | verifier reward·reward_valid·trial 및 step 예외를 구분합니다. | 외부 점수·사유를 보존하고 공통 판정 상태를 연결합니다. 이미 있는 오류·이력 모델을 중복 구현하지 않습니다. [I-03](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec5d110b1704a6eb31e2efedec59a12190df80e1/docs/scoring-policy.qmd) · [I-04](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec5d110b1704a6eb31e2efedec59a12190df80e1/src/inspect_ai/scorer/_metric.py) · [H-02](https://github.com/harbor-framework/harbor/blob/a215bfa03ccc026d22a0f11d5d6c51a8a46f0510/src/harbor/models/trial/result.py) |
| 분모·집계 | unscored와 오류는 기본 accuracy의 분모에서 제외될 수 있습니다. | 여러 단계 reward를 집계하며 유효성 정보도 제공합니다. | 원래 통계와 agent-eval의 계획 대비 성공률을 별도로 표기합니다. native 평균을 전체 목표 성공률로 바꾸지 않습니다. [I-03](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec5d110b1704a6eb31e2efedec59a12190df80e1/docs/scoring-policy.qmd) · [H-02](https://github.com/harbor-framework/harbor/blob/a215bfa03ccc026d22a0f11d5d6c51a8a46f0510/src/harbor/models/trial/result.py) · [H-08](https://www.harborframework.com/docs/tasks/multi-step) |
| 재시도·복구 | checkpoint는 등록된 상태·설정된 sandbox 파일·이벤트를 복구하며 외부 효과는 복구하지 않습니다. 채점 예외가 전체 sample 재실행으로 이어질 수 있습니다. | Job의 반복 수와 retry 설정이 분리되며 확인한 기본 max_retries는 0입니다. regrade는 별도 결과를 만듭니다. | 실행 소유자와 재시도 소유자는 한 곳으로 고정합니다. 기록 읽기·재채점은 실행 재개와 별도 경로입니다. [I-03](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec5d110b1704a6eb31e2efedec59a12190df80e1/docs/scoring-policy.qmd) · [I-05](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec5d110b1704a6eb31e2efedec59a12190df80e1/docs/checkpointing.qmd) · [H-01](https://github.com/harbor-framework/harbor/blob/a215bfa03ccc026d22a0f11d5d6c51a8a46f0510/src/harbor/models/job/config.py) · [H-06](https://github.com/harbor-framework/harbor/blob/a215bfa03ccc026d22a0f11d5d6c51a8a46f0510/src/harbor/trial/regrade.py) |
| 증거 형식 | 공개 log API와 viewer가 메시지·점수·이벤트를 읽습니다. | result.json, artifact manifest, ATIF의 역할이 구분됩니다. | native 파일과 해시를 원본으로 보존하고 최소 인덱스만 만듭니다. 자체 대화 포맷·뷰어 전체를 만들지 않습니다. [I-06](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec5d110b1704a6eb31e2efedec59a12190df80e1/src/inspect_ai/log/__init__.py) · [I-09](https://inspect.aisi.org.uk/log-viewer.html) · [H-02](https://github.com/harbor-framework/harbor/blob/a215bfa03ccc026d22a0f11d5d6c51a8a46f0510/src/harbor/models/trial/result.py) · [H-04](https://github.com/harbor-framework/harbor/blob/a215bfa03ccc026d22a0f11d5d6c51a8a46f0510/src/harbor/models/trajectories/trajectory.py) · [H-05](https://github.com/harbor-framework/harbor/blob/a215bfa03ccc026d22a0f11d5d6c51a8a46f0510/docs-mintlify/jobs/regrade.mdx) |
| 환경·컨텍스트 | sandbox와 agent checkpoint 지원이 있으나 scaffold별 범위가 다릅니다. | 단계 간 환경은 공유하고 대화는 기본 초기화하며 지원 agent는 명시적 resume을 사용합니다. | 환경 상태와 역할 대화 상태를 독립 실험 변수로 저장합니다. [I-05](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec5d110b1704a6eb31e2efedec59a12190df80e1/docs/checkpointing.qmd) · [H-08](https://www.harborframework.com/docs/tasks/multi-step) |
| 재현 | task·model·scorer·log 버전을 보존할 수 있습니다. | JobLock과 task checksum으로 해석된 실행 입력을 고정합니다. | 기존 lock을 참조하고 자체 manifest에는 실험 가설·대응 반복·인계/주입 정책만 보완합니다. [I-02](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec5d110b1704a6eb31e2efedec59a12190df80e1/docs/scoring-workflow.qmd) · [H-02](https://github.com/harbor-framework/harbor/blob/a215bfa03ccc026d22a0f11d5d6c51a8a46f0510/src/harbor/models/trial/result.py) · [H-09](https://github.com/harbor-framework/harbor/blob/a215bfa03ccc026d22a0f11d5d6c51a8a46f0510/src/harbor/models/job/lock.py) |
| 운용 범위 | 확인한 pyproject는 Python 3.11 이상과 MIT입니다. | 확인한 pyproject는 Python 3.12 이상과 Apache-2.0입니다. 환경 공급자가 추가로 필요합니다. | 독립 optional extra/프로세스 경계로 격리합니다. 기본 코어에 Docker나 Harbor를 강제하지 않습니다. |

마지막 행의 소스는 [Inspect pyproject](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec5d110b1704a6eb31e2efedec59a12190df80e1/pyproject.toml)와 [Harbor pyproject](https://github.com/harbor-framework/harbor/blob/a215bfa03ccc026d22a0f11d5d6c51a8a46f0510/pyproject.toml)입니다. 지원 버전 번호와 실제 실행 환경 호환성은 다릅니다.

## 3. 조사로 확인한 중요한 경계

### 3.1 Inspect에는 이미 미판정과 판정 이력이 있습니다

Score.unscored와 reason, history를 활용합니다. 이를 새로 복제하는 대신 과제 기준 ID·증거 참조·사람의 확정 상태를 연결합니다. native NaN·누락·예외를 공통 보고서에서 0점으로 바꾸지 않습니다. [I-03](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec5d110b1704a6eb31e2efedec59a12190df80e1/docs/scoring-policy.qmd) · [I-04](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec5d110b1704a6eb31e2efedec59a12190df80e1/src/inspect_ai/scorer/_metric.py)

Inspect 기본 accuracy와 계획 대비 성공률의 분모는 다를 수 있습니다. 네 번의 계획 중 성공 1, 실패 1, 채점 오류 1, 미판정 1이라면 판정 가능한 결과의 성공률과 계획 전체의 성공률을 따로 산출해야 합니다. 이는 agent-eval 집계 정책이며 Inspect 기본 지표를 잘못된 지표로 분류하지 않습니다.

### 3.2 Harbor도 저장 산출물을 재채점합니다

재채점은 Inspect만의 기능이 아닙니다. Harbor regrade는 새 검증기가 요구하는 산출물이 source manifest에 있어야 하며, 새 검증기는 separate 모드를 사용해야 합니다. 다단계 재채점은 단계 구성이 유지되어야 합니다. 이 조건을 검사한 뒤 native 기능을 호출합니다. 누락 자료를 복원하려고 원래 에이전트를 자동 실행하지 않습니다. [H-05](https://github.com/harbor-framework/harbor/blob/a215bfa03ccc026d22a0f11d5d6c51a8a46f0510/docs-mintlify/jobs/regrade.mdx) · [H-06](https://github.com/harbor-framework/harbor/blob/a215bfa03ccc026d22a0f11d5d6c51a8a46f0510/src/harbor/trial/regrade.py)

### 3.3 기존 Codex 실행 경로의 동일성을 보장해야 합니다

Inspect Bridge는 모델 요청을 라우팅합니다. Harbor의 Codex 구현은 인증 파일을 사용하는 경로도 있으므로 'Harbor는 API 키만 가능하다'고 가정하지 않습니다. 다만 어느 쪽도 현재 Go 어댑터의 세션 키·영수증·도구 프로필과 동일하다는 검증은 없습니다. 첫 실행은 기존 경로를 유지하고, 외부 하네스 경로를 사용할 경우 다른 실행 조건으로 기록합니다. [I-01](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec5d110b1704a6eb31e2efedec59a12190df80e1/docs/agent-bridge.qmd) · [H-07](https://github.com/harbor-framework/harbor/blob/a215bfa03ccc026d22a0f11d5d6c51a8a46f0510/src/harbor/agents/installed/codex.py) · [R-01](https://github.com/shakystar/codex-adapter/blob/main/README.md)

현재 role-orchestrator의 실제 모델 workflow는 고정 작성→검토 경로이며, 명세의 조건부 수정과 도구 실패 주입은 추가 연결이 필요합니다. 저장소 전체의 다른 파일럿과 실제 모델 workflow의 지원 범위를 섞어 해석하지 않습니다. [R-02](https://github.com/shakystar/role-orchestrator/blob/main/README.md)

### 3.4 Inspect Harbor를 범용 호환 계층으로 쓰지 않습니다

Inspect Harbor는 Harbor 과제를 Inspect Sample/Task/Sandbox/Scorer에 연결합니다. 확인한 공식 문서는 multi-step과 Windows 과제를 거부하고, MCP·skills 설정에 경고를 내며, 일부 timeout·환경 필드를 무시한다고 명시합니다. [B-01](https://meridianlabs-ai.github.io/inspect_harbor/tasks.html) · [B-02](https://meridianlabs-ai.github.io/inspect_harbor/agents.html)

따라서 첫 버전의 기본 연결로 채택하지 않습니다. 후속 단일 단계 과제에 사용할 때에는 변환에서 손실되는 필드를 명세와 대조하고 필수 필드가 손실되면 거부합니다. Harbor의 모든 기능이 Inspect에서 유지된다고 표시하지 않습니다.

## 4. 구현 소유권

| 구분 | 범위 | 하지 않을 중복 개발 |
| --- | --- | --- |
| Inspect 재사용 | 공개 log reader/writer, Score·scorer 호출, 저장 로그 재채점, native viewer | 자체 모델 provider 집합·범용 채점 실행기·대화 로그 UI |
| Harbor 후속 재사용 | 환경 준비/정리, task package, agent 실행, verifier/regrade, ATIF·artifact manifest | 자체 컨테이너 공급자 계층·CLI 에이전트 설치기 |
| 기존 프로젝트 재사용 | workflow·worker·세션·실행 영수증과 명시적 복구 | 별도 업무 scheduler·Codex protocol 구현 |
| agent-eval 직접 개발 | 실험 manifest·조건 비교·역할 인계 정책·주입 적용 계약·native ID 연결·검토 확정·평가자 신뢰성 보고 | 모든 native 필드를 복사한 또 하나의 거대 공통 스키마 |
| 과제 묶음에서 개발 | 완료 조건·필수 인계·상태/산출물 검사·기준 사례 | 도메인 정답을 코어에 내장 |

단순 형식·해시·참조 검사는 코어에서 직접 처리합니다. 과제의 의미 평가와 범용 scorer 실행은 Inspect를 우선 활용합니다. 최종 보고서와 검토 원장은 제품 정책이므로 agent-eval이 소유합니다.

## 5. 첫 연결 구조

```text
agent-eval 실험 manifest
  ├─ 기존 실행 어댑터 → role-orchestrator → role-runtime → codex-adapter
  │                   └─ 영수증·산출물·이벤트
  └─ 저장 기록 가져오기
          ↓
  원본 참조 + 최소 증거 인덱스
          ↓
  Inspect 평가 어댑터 → native 점수·로그·뷰어
          ↓
  기준별 상태 연결 → 사람의 검토·신뢰성 → 조건별 비교 보고서

후속: Harbor 실행 어댑터 → 환경·agent·verifier → native 기록 가져오기
```

기존 workflow 실행 모드에서 Inspect는 업무 실행·재시도의 소유자가 아닙니다. 외부 실행을 하나의 solver로 감싸는 최적화는 M0에서 호출 횟수·복구 계약을 검증한 뒤에만 사용합니다. 초기 연결은 완료/실패 증거의 사후 평가가 기본입니다.

하나의 논리 실행에 execution_owner를 하나만 지정합니다. Harbor 모드이면 Harbor가 trial 실행과 환경을 소유하고, 기존 runtime 모드이면 기존 시스템이 소유합니다. agent-eval은 계획된 반복 요청과 결과 비교만 담당하며 내부 시도를 중첩 재시도하지 않습니다.

## 6. 공통 매핑 원칙

| 외부 정보 | agent-eval 처리 |
| --- | --- |
| Inspect sample/epoch 또는 Harbor trial | 실험·조건·반복 ID에 연결하고 native ID를 보존합니다. |
| Inspect Score와 reason/history | 판정 근거와 native 원본으로 참조합니다. 사람의 확정은 별도 기록입니다. |
| unscored·오류·없는 score | 원인에 따라 판단 불가·평가기 오류·해당 없음/미평가로 명시합니다. 단순 미기록은 해당 없음으로 추정하지 않습니다. |
| Harbor verifier reward 및 reward_valid | 유효성·예외와 함께 보존합니다. reward 숫자만으로 성공을 확정하지 않습니다. |
| ATIF session_id·trajectory_id·하위 참조 | 실행과 trajectory 문서의 ID를 구분해 연결합니다. 모든 하위 문서가 같은 session을 공유할 수 있습니다. |
| 시간·사용량·비용 | 측정 경계와 누락 여부를 보존합니다. 단계별 일부 비용만 알려지면 부분합으로 표시합니다. |
| native 집계 | 참고 지표로 보존하며 제품 성공률은 사전 정의된 분모로 별도 산출합니다. |

Harbor의 확인한 합산 코드는 알려진 단계 값만 더할 수 있습니다. 따라서 전체 비용의 숫자가 있어도 모든 단계가 측정되었다고 추론하지 않습니다. [H-02](https://github.com/harbor-framework/harbor/blob/a215bfa03ccc026d22a0f11d5d6c51a8a46f0510/src/harbor/models/trial/result.py)

## 7. 통합 전 필수 검증

| ID | 확인할 경로 | 통과 조건 |
| --- | --- | --- |
| C-01 | 저장 기록 가져오기 | 정상·실패·중단·미판정·부분 점수·중복·내용 충돌이 보존됩니다. |
| C-02 | Inspect 재채점 | 저장 산출물을 두 기준으로 평가해 원본과 이전 판정이 유지되고 과제 실행 호출은 0회입니다. |
| C-03 | 평가 오류 | 채점 오류를 일으켜도 기존 runtime 작업은 재실행되지 않습니다. |
| C-04 | 분모 매핑 | 계획 수·실행 수·판정 가능 수·미판정 수와 양쪽 집계 차이를 설명할 수 있습니다. |
| C-05 | 실행 동일성 | 기존 실행 어댑터가 모델·인증·역할 세션·도구 프로필을 바꾸지 않고 영수증을 연결합니다. |
| C-06 | 협업·주입 | 실제 입력 참조·필수 인계·주입 전후 증거와 적용 횟수를 확인합니다. 미지원 기능은 실행 전에 거부합니다. |
| C-07 | 검증 자료 분리 | 과제 실행 입력에 정답과 평가 전용 기준이 전달되지 않습니다. 가져오기만으로 로그가 가리키는 코드나 endpoint를 실행하지 않습니다. |
| C-08 | Harbor 후속 조건 | 환경 reset·별도 검증·artifact 누락·regrade·단계 실패·부분 비용을 확인합니다. |
| C-09 | 변환 호환성 | Inspect Harbor를 사용할 경우 필수 필드가 무시되거나 미지원이면 거부합니다. |

M0에서는 C-01~04·07의 fixture 검증과 C-05~06의 capability 대조를 수행합니다. C-05~06의 실제 모델 실행 확인은 M3, C-08~09는 Harbor 도입 시 수행합니다. M0의 실제 실행 결과와 제한은 [검증 기록](../validation/m0.md)에 보존합니다. C-05~06의 실제 모델 통합을 완료한 것은 아닙니다.

## 8. 재검토 조건

Inspect 어댑터가 원본/판정 의미를 보존하지 못하거나, 모델 라우팅을 강제로 바꾸거나, 기존 작업의 재실행을 막을 수 없으면 채택 범위를 줄이고 불일치를 기록합니다. 외부 라이브러리 fork는 첫 대응으로 선택하지 않습니다.

Harbor는 실제 환경 조작 과제가 생기고 reset·검증기·산출물 경계를 확인할 때 도입합니다. Inspect와 Harbor 사이의 자동 변환 범위가 넓어지더라도 같은 호환성 검사를 유지합니다.

## 9. 출처

- [I-01: Inspect Agent Bridge](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec5d110b1704a6eb31e2efedec59a12190df80e1/docs/agent-bridge.qmd)
- [I-02: Inspect scoring workflow](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec5d110b1704a6eb31e2efedec59a12190df80e1/docs/scoring-workflow.qmd)
- [I-03: Inspect scoring policy](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec5d110b1704a6eb31e2efedec59a12190df80e1/docs/scoring-policy.qmd)
- [I-04: Inspect Score 계약](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec5d110b1704a6eb31e2efedec59a12190df80e1/src/inspect_ai/scorer/_metric.py)
- [I-05: Inspect checkpointing](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec5d110b1704a6eb31e2efedec59a12190df80e1/docs/checkpointing.qmd)
- [I-06: Inspect log API](https://github.com/UKGovernmentBEIS/inspect_ai/blob/ec5d110b1704a6eb31e2efedec59a12190df80e1/src/inspect_ai/log/__init__.py)
- [I-07: Inspect multi-agent](https://inspect.aisi.org.uk/multi-agent.html)
- [I-08: Inspect intervention](https://inspect.aisi.org.uk/intervention.html)
- [I-09: Inspect viewer](https://inspect.aisi.org.uk/log-viewer.html)
- [H-01: Harbor job config](https://github.com/harbor-framework/harbor/blob/a215bfa03ccc026d22a0f11d5d6c51a8a46f0510/src/harbor/models/job/config.py)
- [H-02: Harbor trial result](https://github.com/harbor-framework/harbor/blob/a215bfa03ccc026d22a0f11d5d6c51a8a46f0510/src/harbor/models/trial/result.py)
- [H-03: Harbor task config](https://github.com/harbor-framework/harbor/blob/a215bfa03ccc026d22a0f11d5d6c51a8a46f0510/src/harbor/models/task/config.py)
- [H-04: Harbor ATIF](https://github.com/harbor-framework/harbor/blob/a215bfa03ccc026d22a0f11d5d6c51a8a46f0510/src/harbor/models/trajectories/trajectory.py)
- [H-05: Harbor regrade](https://github.com/harbor-framework/harbor/blob/a215bfa03ccc026d22a0f11d5d6c51a8a46f0510/docs-mintlify/jobs/regrade.mdx)
- [H-06: Harbor regrade implementation](https://github.com/harbor-framework/harbor/blob/a215bfa03ccc026d22a0f11d5d6c51a8a46f0510/src/harbor/trial/regrade.py)
- [H-07: Harbor Codex adapter](https://github.com/harbor-framework/harbor/blob/a215bfa03ccc026d22a0f11d5d6c51a8a46f0510/src/harbor/agents/installed/codex.py)
- [H-08: Harbor multi-step](https://www.harborframework.com/docs/tasks/multi-step)
- [H-09: Harbor job lock](https://github.com/harbor-framework/harbor/blob/a215bfa03ccc026d22a0f11d5d6c51a8a46f0510/src/harbor/models/job/lock.py)
- [B-01: Inspect Harbor task mapping](https://meridianlabs-ai.github.io/inspect_harbor/tasks.html)
- [B-02: Inspect Harbor agents](https://meridianlabs-ai.github.io/inspect_harbor/agents.html)
- [R-01: 기존 Codex 실행 계약](https://github.com/shakystar/codex-adapter/blob/main/README.md)
- [R-02: 기존 orchestration 상태](https://github.com/shakystar/role-orchestrator/blob/main/README.md)
