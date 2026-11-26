# M2 독립 재현 결과

고정 후보의 합성 인프라, 기존 기록 호환성, 사용자 요청·선제 신호 경로에 대해 acl-014와 최종 판정자 acl-005가 인수했다. 최초 검토는 계정 확인 단계에서 보류됐고, 11월 26일 계정 라우팅 복구 후 독립 판정이 완료됐다. 당시 사용량 완전성은 미인수였다. M2 후보의 회귀 시험은 157건, 실패와 건너뜀은 각각 0건이었다. [시험 원본](m2-integration-evidence.json) · [후속 품질 검토](M2-usage-quality.md)

검증한 세 커밋은 다음과 같다. [codex-adapter f338b29](https://github.com/shakystar/codex-adapter/commit/f338b2908ff32094514763000bf71da4d7d4bcaf) · [role-runtime 4a457bb](https://github.com/shakystar/role-runtime/commit/4a457bb576376366989ad6d53ed291f59848d4a0) · [role-orchestrator 753fe02](https://github.com/shakystar/role-orchestrator/commit/753fe029c889ee5eff3728cc3c34e52b7edf1b43)


시험 대상은 원격 후보 브랜치에서 새로 체크아웃했다. 새 Go workspace에 어댑터와 런타임을 함께 등록하고, 그 workspace에서 빌드한 브리지·워크플로·프로브를 Python 시험에 지정했다. Go 도구체인·의존성 캐시와 Python 가상환경은 재사용했다. 공급자 프로세스 자리는 네트워크를 사용하지 않는 합성 JSON-RPC 서버가 맡았다. 요청과 선제 신호의 입력은 v0.3.0에 보관한 고정 사례다.

| 검증 항목 | 관측 결과 |
|---|---|
| 빌드와 기본 회귀 | M1 고정 조합에서 Go vet·race 통과, Python 32개 모듈 156건 통과. 어댑터 모듈의 실제 경로가 새 체크아웃과 일치했다. |
| 중복과 반환 유실 | 같은 요청 두 번은 제출 1건과 추가 제출 0건이었다. 같은 출력을 낸 독립 완료 두 건은 2턴으로 거부했다. 시작 응답 유실 뒤 브리지를 재시작해 같은 시도를 제출했을 때 신규 제출은 0건이고 판정은 미확인이었다. |
| 과거 기록 | v0.3.0 11건과 v0.3.1 32건의 기존 판정·산출물·영수증 해시가 일치했다. 원본 바이트를 보존했고, 이전 기록에 없는 턴 증빙은 미확인으로 읽었다. |
| 종단 경로 | 사용자 의뢰 5단계와 선제 신호 6단계에서 배정·시도·역할·원문 영수증·턴과 결과를 대조했다. 각 단계의 입력에 직전까지의 영수증 전체가 있었고, 마지막 결정은 해당 사례의 패킷을 참조했다. 두 합성 사례의 업무 결정은 모두 추가 자료 대기였다. |
| 잘못된 참조 | 다른 배정이나 역할 개정은 검증기가 실패로 판정했다. 오래된 초안의 리뷰와 다른 사례의 최종 패킷은 연구 경로에서 종단 보류로 종료했고 잘못 연결된 결정을 확정하지 않았다. |
| 검토 독립성 | 작성 이력에 검토자가 포함된 경우 검토 턴 0회로 재배정을 요청했다. 최초 후보는 자발 신고를 일반 오류로 종료했다. 수정 후보에서는 현재 초안에 의견 없이 이해충돌만 신고해도 검토 영수증과 신고를 보존하고 재배정을 요청한다. 같은 체크포인트를 다시 읽을 때 추가 턴은 0회다. |

합성 사용량은 마지막으로 일치한 턴 사용량 알림을 시험하기 위한 값이다. 서비스 과금·모델 품질·제공자 내부 호출 횟수는 측정 대상에서 제외했다. 서명된 원문과 신뢰키 이력 검증은 미확인이다. 런타임·독립 검증 담당이 해당 근거를 제출할 때까지 서명 기준은 보류한다.

## 독립 재현 방법

세 저장소를 서로 이웃한 디렉터리에 체크아웃하고 아래 증거 파일의 `checked_commits`를 사용한다. Go 1.26.11과 오케스트레이터 의존성이 설치된 Python 환경에서 실행한다. 작업 디렉터리는 세 체크아웃의 부모다.

```sh
go work init ./codex-adapter ./role-runtime
(cd codex-adapter && go vet ./... && go test -race -count=1 ./...)
(cd role-runtime && go vet ./... && go test -race -count=1 ./...)
(cd role-runtime && go list -m -f '{{.Dir}}' github.com/shakystar/codex-adapter)
(cd role-runtime && go build -o ../candidate-bridge ./cmd/runtime-bridge)
(cd role-runtime && mkdir -p bin && go build -o bin/runtime-workflow ./cmd/runtime-workflow && go build -o bin/workflow-probe ./experiments/workflowprobe)
(cd role-orchestrator && ROLE_RUNTIME_BIN="$PWD/../candidate-bridge" python -m unittest discover -s tests -v)
```

연구 경로 재현에는 같은 디렉터리에 `agent-eval`과 `agent-collaboration-lab` 체크아웃도 둔다. 명부 개정은 재현 도구에 고정돼 있다. 다음 예시의 상태 디렉터리는 새로 생성된다.

```sh
milestone=agent-eval/docs/milestones
python "$milestone/v0.3.2/reproduction/replay.py" --orchestrator role-orchestrator --bridge candidate-bridge --lab agent-collaboration-lab --fixture "$milestone/v0.3.0/cases/request-fixture.json" --state ./m2-request
```

선제 신호는 `signal-fixture.json`으로 바꾼다. 매번 새 상태 경로를 주고 `--fault author`, `--fault self`, `--fault stale`로 독립성 및 구개정 반례를 재현한다. 다른 사례의 결정 참조는 `--fault other --other-packet`에 반대 경로의 패킷 해시를 전달한다. 재현 도구는 합성 peer의 배정별 호출 원장과 네이티브 영수증을 대조한 후, 동일 체크포인트 재개 시 신규 호출이 없는지 확인한다.
