# M3 호출 수 사전 검증

후속 구현과 재현 명령은 [배정별 채점 적격성](M3-call-admission.md)에 정리했다.

김가온(acl-014)은 실모델 역할 비교 착수를 보류했다. 같은 상태 디렉터리와 동일한 배정·시도 키를 사용했다. 최초 요청이 오프라인 합성 서버의 turn/start 수신 원장에 기록된 뒤 응답을 대기시키고 두 번째 브리지 프로세스에서 같은 바이트를 제출했다. 각 시나리오는 한 번씩 실행했다.

| 조건 | 합성 서버의 실제 수신 | 재시작 후 추가 제출 | 영수증 판정 |
|---|---:|---:|---|
| 정상 완료 | 1 | 0 | 캐시 반환, accept |
| 시작 응답 전 서버 종료 | 1 | 0 | execution_blocked, hold |
| 전송 직전에 같은 요청을 두 번 전달하고 한 응답만 반환 | 2 | 0 | 1턴 accept. 호출 원장 대조는 reject |

재심 조건은 독립적으로 집계한 호출 수를 A/B 최종 승인 조건에 연결하는 것이다. 정상 재제출, 시작 응답 유실, 이중 전달의 최종 판정을 같은 빌드로 대조한다. 제공자 내부 호출·과금과 역할별 품질은 측정하지 않았다. [판정·실행 근거](m3-call-boundary-preflight.json)

## 재현

병합된 role-runtime에서 GOWORK=off로 cmd/runtime-bridge를 빌드한다. PREFLIGHT_BRIDGE에 그 실행 파일의 절대 경로, PREFLIGHT_ORCHESTRATOR에 고정된 오케스트레이터 체크아웃의 절대 경로를 지정한다. 해당 Python 의존성 환경에서 아래 명령을 각각 새 경로로 실행한다.

```sh
python reproduction/call-boundary/check.py ./natural
python reproduction/call-boundary/control.py ./wire-fault
```
