# v0.1.0 · 승인한 수정 작업 한 건의 실행과 복구

**상태** 후보 검증 완료 · 병합과 릴리스 결정 대기

## 목표와 범위

저장된 `revise` 제안을 명시적으로 승인해 한 번 수정하고, 프로세스를 재시작한 뒤 같은 결과를 조회한다. 실행·평가 계약은 [기능 명세와 담당 작업](https://github.com/shakystar/role-orchestrator/blob/abf32919ff0a4e3bd96b2c0d58b8a92d45e805a6/docs/features/approved-revision.md)에 둔다. [공통 개발 정책](https://github.com/shakystar/agent-collaboration-lab/blob/c541f5ba978d06bc0e5ce7a1c1df0dff1166149f/docs/development-policy.md)을 적용한다.

## 기준 조합과 검증 후보

### 11월 22일 기준 조합

아래 네 SHA는 [11월 22일 기준 실행](../../validation/issue-1-20261122/README.md)에 사용한 값이다.

| 레포 | 기준 커밋 |
|---|---|
| agent-eval | [6db70ed063b2d993670f56408da0493524a02bfa](https://github.com/shakystar/agent-eval/commit/6db70ed063b2d993670f56408da0493524a02bfa) |
| role-orchestrator | [66657b78210fd16697175abec4b1807e95ed1a28](https://github.com/shakystar/role-orchestrator/commit/66657b78210fd16697175abec4b1807e95ed1a28) |
| role-runtime | [7b2f83702fac83e4004bf7b105a343872e3e53d6](https://github.com/shakystar/role-runtime/commit/7b2f83702fac83e4004bf7b105a343872e3e53d6) |
| codex-adapter | [2b8c204b0cb7e3c63c60a3fa7923e4e9ca4d02bb](https://github.com/shakystar/codex-adapter/commit/2b8c204b0cb7e3c63c60a3fa7923e4e9ca4d02bb) |

### 현재 검증 후보

| 레포 | 후보 커밋 |
|---|---|
| agent-eval | `f217804010233c727fc7b2e44d6c05776cc93bf0` |
| role-orchestrator | `6935f81582aa5e1f0e8414cbf4bba31e47089fd9` |
| role-runtime | `722c9f620a707a8dc42c43a44f3666a3ba4fc87e` |
| codex-adapter | `17b36ab24d29f45799af705cca2e35c35af1a609` |

검증한 이미지의 다이제스트는 `sha256:c7f96f710c6652f7f427cad4384ef24c2b8828d7457fcd4bdabbc514d38816a3`. 표준 M3 빌더에는 adapter 후보 SHA를 명시한다. 빌드된 바이너리의 모듈 정보 확인 절차는 [adapter 고정 검증](../../validation/m3-adapter-pin.md)을 따른다. 팀 검증에서는 어댑터에 모델의 추론 강도 전달을 추가했다. 이미지의 두 Python 패키지 파일 38개는 후보 커밋의 Git 객체와 해시가 일치했다.

## 완료 조건과 결과

| 시나리오 | 완료 조건 | 후보 검증 결과 |
|---|---|---|
| 승인 후 수정 | 올바른 작성자와 계약, 성공 영수증 및 산출물 일치 | 실제 Go runtime과 합성 응답을 사용한 네이티브 승인 시나리오 7개 통과. [승인 증거](evidence/approval.json) |
| 중복·동시 승인 및 중단 | 동일 키의 추가 제출 0회, 불확실 상태 보존 | 네이티브 승인 시나리오로 검증했다. 별도 직접 RPC 검사에서는 프로세스 재시작 후 성공·실패 건을 각각 재요청해 두 번째 실행이 없음을 확인했다. [승인 증거](evidence/approval.json) · [재시작 증거](evidence/restart.json) |
| 과거 실행 회귀 | 기존 제안 조회, M3 기본 비교와 수정 분기 재현 | fixture 9슬롯·30단계, Codex 9슬롯·18단계로 회귀를 확인했다. [fixture 회귀](evidence/fixture-regression.json) · [Codex 회귀](evidence/codex-regression.json) |

## M1~M6 개발·검증 결과

| 마일스톤 | 결과와 검증 범위 |
|---|---|
| M1 · 실행 및 영수증 | 실행 `r-af72a4c620dc4bc18c31707c5cd1fdb6`, 시도 `a-f058d7e523f02b634e18ebe745a81b14`의 상태는 `succeeded`였다. 실제 멤버는 `acl-004`, 실제 역할 버전은 `v1`, 기록 버전은 `2`였다. |
| M2 · 실제 모델 프로필 확인 | 영수증에 연결된 로컬 세션의 `turn_context`에서 `m2-live-02`는 `gpt-6.2-sol / medium`, `m2-live-review`는 `gpt-6.2-astra / high`로 관측됐다. 확인 범위는 이 두 작업이다. |
| M3 · 비교 및 수정 분기 회귀 | Linux M3 검사 15/15 통과, 검토 결과는 `accept`였다. 기준 실행의 기본 비교와 수정 분기는 위 fixture 및 Codex 회귀 증거로 추적한다. |
| M4 · 격리된 핸드오프 검증 | 고유 핸드오프 사례 28개를 33회 실행했다. 정상 `passed`, 결함 `test_failed`, 충돌 `patch_failed`, 오래된 입력 `skipped`, 팀 패치 `passed`로 기록됐다. |
| M5 · 승인 실행과 복구 | 검토 결과는 `approve`였다. 네이티브 승인 7개 시나리오가 통과했고, 직접 RPC 재시작 검사에서는 성공·실패 결과 모두 재실행 없이 조회됐다. |
| M6 · 모델 비교 | 동일한 합성 7행 과제에서 `gpt-6.2-sol / medium`과 `gpt-6.2-astra / medium` 모두 기대값 `[B, C]`와 일치했다. 두 모델 모두 누락·오탐·재작업은 각각 0이었다. |

| M6 관측 프로필 | 시간 | 입력 토큰 | 캐시 입력 / 캐시 쓰기 입력 | 출력 토큰 | 추론 출력 토큰 | 총 토큰 |
|---|---:|---:|---:|---:|---:|---:|
| `gpt-6.2-sol / medium` | 7.271초 | 6011 | 0 / 0 | 13 | 0 | 6024 |
| `gpt-6.2-astra / medium` | 11.11초 | 6011 | 0 / 0 | 13 | 0 | 6024 |

그 밖에 Go runtime의 `scripts/check.sh`와 adapter의 vet/race 검사가 통과했고, Python orchestrator는 86/86을 통과했다. Eval 로컬 검사 집계는 63건이며, 이 중 34건은 선택 검사로 건너뛰었다. 별도 Linux 실행에서는 Inspect 44/44와 M3 15/15가 통과했다. [통합 검증 증거](evidence/validation.json)

## 재현 절차

아래 명령은 세 레포와 `agent-eval`이 나란히 있는 상위 디렉터리에서 실행하는 예다. 먼저 각 레포가 **현재 검증 후보** 표의 커밋을 가리키는지 확인한다. `m3-v0.1.0-candidate`는 재현용 로컬 이미지 태그다.

```sh
python agent-eval/containers/linux/build_m3.py \
  --runtime ./role-runtime \
  --orchestrator ./role-orchestrator \
  --adapter ./codex-adapter \
  --adapter-commit 17b36ab24d29f45799af705cca2e35c35af1a609 \
  --tag m3-v0.1.0-candidate

(cd role-runtime && scripts/check.sh)
(cd codex-adapter && go vet ./... && go test -race ./...)
```

fixture 및 Codex 회귀의 정확한 driver 실행 명령과 설정은 [원래 실행 절차](../../validation/issue-1-20261122/README.md)를 따른다. 보고서 검증은 증거 파일을 대상으로 하는 별도 평가이며, 원래 driver를 실행해 동작을 평가하는 것과 구분한다. 아래 명령은 해당 경로가 있는 저장소 루트에서 기존 승인 증거를 재검사하며, driver나 재시작 시나리오를 다시 실행하지 않는다.

```sh
python tests/verify_approval_evidence.py docs/milestones/v0.1.0/evidence/approval.json
```

## 한계와 마감 판단

- 기본 네트워크에서 처음 시도한 Codex 실행은 9슬롯 모두 `not_started`였다. 컨테이너 내부 DNS만 TLS에 응답하는 호스트로 고정한 뒤 최종 네 SHA 조합이 통과했다.
- 재시작 후 중복 실행이 없다는 결론은 검증한 승인 시나리오와 직접 RPC의 성공·실패 사례에 한정한다. M6 비교는 동일한 합성 과제에서 모델별 한 번씩 측정한 값이므로, 시간 차이나 토큰 사용량을 일반적인 성능 차이로 해석하지 않는다.
- 이 문서는 후보 조합의 검증 결과를 기록한다. 작업 브랜치 및 `main` 병합 여부와 v0.1.0 릴리스 여부는 사람이 결정한다. 후보 검증 통과나 M3·M5 검토 결과만으로 병합 또는 릴리스가 승인되거나 완료된 것은 아니다.
