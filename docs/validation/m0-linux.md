# M0 Docker/Linux 통합 검증

2026-11-20. Windows 호스트의 기존 WSL2 Ubuntu-22.04 Docker Engine에서 검증했습니다. Windows 네이티브 포팅 대신 Linux 실행 경로를 고정했습니다.

## 결과

| 검사 | 결과 |
| --- | --- |
| Go engine/control/lifecycle vet 및 race 검사 | 통과 |
| 기존 workflow 합성 acceptance | 19/19 통과, skip 0 |
| 실제 Go + LangGraph/SQLite + Inspect fixture | 통과 |
| 실제 Codex 작성→검토 | 2개 작업 완료, receipt generation 각각 1 |
| 실제 artifact hash 및 인계 원본 hash | 일치 |
| Inspect 로그 roundtrip·추가 판정·채점 오류·변조 거부 | 통과 |
| 재채점 후 추가 실행 | 0 |
| runtime 재시작 및 새 graph poll 후 추가 실행 | 0 |
| 재채점·재시작 전후 model-status | 동일 |

Inspect는 별도 프로세스에서 완료된 증거만 채점했습니다. 실행은 기존 Go runtime→codex-adapter→Codex app-server가 담당했습니다. 외부 채점 모델 호출은 0입니다. native 판정과 원본 로그 해시는 보존했습니다.

## 환경과 증거

- [고정 소스·이미지·검사 manifest](linux/manifest.json)
- [19개 acceptance 결과](linux/workflow-acceptance.json)
- [fixture 통합 결과](linux/fixture-inspect-integration.json)
- [실제 Codex 통합 결과](linux/codex-inspect-integration.json)
- [빌드와 실행 절차](../../containers/linux/README.md)

실제 검증 이미지: `sha256:04f592fbe15d1bac006d5c4bc3a1668005b501a27e427deedc9b670ec9899a2d`.

Go 1.26.11, Python 3.12.3, uv 0.13.9와 소스 commit을 고정했습니다. orchestrator는 원래 uv.lock 환경, Inspect는 별도 venv를 사용합니다. Linux Inspect에는 이전 Windows SQLite 경로 패치를 적용하지 않았습니다. shallow checkout 때문에 Inspect 패키지 버전의 SCM 카운트가 dev1로 표시되며, 이전 dev17과 소스 commit은 같습니다.

Codex 0.167.0 및 기존 설정의 `gpt-6-astra`/`medium`, runtime의 advisory 도구 프로필을 사용했습니다. 인증·설정·실행 바이너리는 읽기 전용으로 마운트했습니다. 인증 정보와 모델 원문은 Git이나 이미지에 넣지 않았습니다. 원본 실행·Inspect 증거는 로컬 Docker volume `agent-eval-live-20261120-m0`에 보존했습니다.

## 실패 이력

첫 실제 실행 `/state/live-001`은 `account_read / workspace_routing_unauthorized`로 실패했습니다. 실행 상태는 `not_started`였으며 모델 작업을 제출하지 않았습니다. 자동 재시도하지 않았습니다.

동일 SDK의 account/read doctor가 WSL 및 컨테이너에서 성공한 뒤, 인증·설정·네트워크 변경 없이 별도 상태 `/state/live-002`로 새 실험을 수행하여 통과했습니다. 최초 실패 원인은 영구 해결됐다고 단정하지 않습니다. 두 실험의 상태를 모두 보존했습니다.

## 판정 범위

이번 통과는 고정 workflow의 실행·인계·평가 재사용 계약에 한정됩니다. 임의 과제 주입, 자동 수정 루프, 직무 과제 타당성, 사람 기준의 의미 평가 신뢰성은 미검증입니다. 이 결과로 스킬 효과나 모델 성능 우위를 주장하지 않습니다. M1~M4는 완료 처리하지 않습니다.

runtime 고정 commit은 `fix/m0-windows-control-build` 브랜치에 보존했으며 main에는 병합하지 않았습니다. Docker 이미지는 로컬에만 존재합니다.
