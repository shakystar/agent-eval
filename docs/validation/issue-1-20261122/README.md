# 이슈 #1 · 병합 후 네 저장소 통합 검증

2026-11-22에 네 저장소의 `main`을 고정하고 합성 결제 점검 공지를 실제 Codex로 작성·검토했습니다. 실모델 9건(18단계)과 fixture 9건(30단계)이 모두 완료됐습니다. 실패·미실행은 각각 0건입니다. 네트워크와 인증을 제거한 컨테이너에서 모델을 다시 호출하지 않고 전체 48단계의 실행 기록을 대조했습니다. [검증 이슈](https://github.com/shakystar/agent-eval/issues/1)

## 검증 대상과 빌드

| 구성요소 | 실행에 고정한 커밋 |
|---|---|
| agent-eval | [6db70ed063b2d993670f56408da0493524a02bfa](https://github.com/shakystar/agent-eval/commit/6db70ed063b2d993670f56408da0493524a02bfa) |
| role-orchestrator | [66657b78210fd16697175abec4b1807e95ed1a28](https://github.com/shakystar/role-orchestrator/commit/66657b78210fd16697175abec4b1807e95ed1a28) |
| role-runtime | [7b2f83702fac83e4004bf7b105a343872e3e53d6](https://github.com/shakystar/role-runtime/commit/7b2f83702fac83e4004bf7b105a343872e3e53d6) |
| codex-adapter | [2b8c204b0cb7e3c63c60a3fa7923e4e9ca4d02bb](https://github.com/shakystar/codex-adapter/commit/2b8c204b0cb7e3c63c60a3fa7923e4e9ca4d02bb) |

WSL2 Ubuntu 22.04의 Docker Engine 29.1.3, `linux/amd64`, Codex CLI 0.167.0을 사용했습니다. 이슈 개설 때의 SHA 대신 실행 시작 시점의 SHA를 사용했습니다. 빌더는 네 Git 커밋에서 소스를 추출하고, Go 빌드 안에서만 어댑터 모듈을 고정한 로컬 소스로 교체합니다. Python 패키지·과제 파일 43개를 Git blob과 대조하고 Go 바이너리의 모듈 교체 정보·해시와 bridge capability를 확인했습니다. Linux M3 회귀 검사도 15/15 통과했습니다. [이미지·소스 대조 기록](image-provenance.json)

## 조건별 결과

| 조건 | fixture 완료 | 실모델 완료 | 실제 관측 |
|---|---:|---:|---|
| 단독 작성 | 2/2 | 2/2 | 작성 영수증과 저장 산출물이 일치했습니다. |
| 작성·검토 | 2/2 | 2/2 | 두 건 모두 첫 검토에서 수락했습니다. |
| 검토 시 자료 추가 | 2/2 | 2/2 | 두 건 모두 검토 요청에 자료가 한 번 추가됐고 첫 검토에서 수락했습니다. |
| 인계 읽기 장애 | 2/2 | 2/2 | 두 건 모두 인계 읽기 오류 1회 후 같은 문서를 다시 읽고 수락했습니다. |
| 별도 수정 시나리오 | 1/1 | 1/1 | 첫 검토에서 새 요구사항을 보고 수정을 요청했습니다. 작성자가 초안에 없던 `PAY-427`을 추가했고 최종 검토에서 수락했습니다. |

fixture의 검토 결정은 미리 설정했습니다. 실모델에는 fixture 출력을 전달하지 않았고, 자료와 장애 주입 위치만 설정했습니다. 단계별로 네이티브 bridge에서 읽은 요청·영수증 바이트, 시도 ID, 입력과 출력, 인계 문서 해시를 저장 증거와 대조했습니다. 최초 채점과 별도 ID의 재채점에서 각 백엔드의 9건 모두 `has-notice=met`이었고, 판정·증거 해시와 최초 평가 기록이 유지됐습니다. [fixture 증거](fixture-results.json) · [실모델 증거](codex-results.json)

## 이전 실행과 남은 문제

- 11월 20일과 이번 실모델 결과는 모두 기본 비교 8건과 별도 수정 1건, 총 18단계입니다. 이번에는 Docker 기본 네트워크로 완료했고 컨테이너별 주소 고정이 필요하지 않았습니다. 장기 연결 안정성은 측정하지 않았습니다. [이전 실행 기록](../m3/linux-results.json)
- 현재 표준 M3 빌더는 인접한 `codex-adapter` 체크아웃을 입력으로 받지 않습니다. 표준 빌드만 수행하면 `role-runtime/go.mod`의 이전 의존성이 선택됩니다. 이 기록의 [네 커밋 빌더](build_four_commits.py)로 실험 조합을 재현할 수 있습니다. 고정 M2 베이스 이미지가 선행 조건입니다.
- `has-notice`는 비어 있지 않은 공지의 존재를 검사합니다. 공지의 전반적 정확성, 협업에 따른 품질 향상, 토큰·비용은 이번 결과의 측정 범위 밖입니다. 실행 중 관측한 턴 컨텍스트 11개는 모두 `gpt-6-astra`였으며 전체 18단계의 모델명을 개별 보존하지 않았습니다.

## 재현

네 저장소를 같은 상위 디렉터리에 두고 이 보고서가 포함된 `agent-eval`에서 실행합니다. 빌더는 현재 작업 파일 대신 위 커밋의 Git 객체를 사용합니다. Linux용 Codex 실행 파일과 인증·설정 경로를 각각 `CODEX_BIN`, `CODEX_AUTH`, `CODEX_CONFIG` 환경변수에 지정합니다. 결과 경로는 컨테이너 UID 1000이 쓸 수 있는 새 디렉터리를 사용합니다.

```bash
set -eu
D="$PWD/docs/validation/issue-1-20261122"
python3 "$D/build_four_commits.py"
python3 "$D/verify_four_commits.py"
IMAGE=$(docker image inspect agent-eval-m3:inventory-four-6db70ed --format '{{.Id}}')
WORK=$(mktemp -d)
mounts=(--mount "type=bind,src=$D/driver.py,dst=/issue1/driver.py,readonly"
        --mount "type=bind,src=$WORK,dst=/work")
runner=(--entrypoint /opt/src/role-orchestrator/.venv/bin/python "$IMAGE" /issue1/driver.py)
docker run --rm --network none "${mounts[@]}" "${runner[@]}" run fixture /work/fixture
docker run --rm --network none "${mounts[@]}" "${runner[@]}" verify fixture /work/fixture
docker run --rm "${mounts[@]}" \
  --mount "type=bind,src=$CODEX_BIN,dst=/usr/local/bin/codex,readonly" \
  --mount "type=bind,src=$CODEX_AUTH,dst=/home/evaluator/.codex/auth.json,readonly" \
  --mount "type=bind,src=$CODEX_CONFIG,dst=/home/evaluator/.codex/config.toml,readonly" \
  "${runner[@]}" run codex /work/codex
docker run --rm --network none "${mounts[@]}" "${runner[@]}" verify codex /work/codex
```

각 `verify`는 원본을 다시 제출하지 않고 새로운 검증 디렉터리에 결과를 씁니다. 공개 결과에는 단계별 시도 식별자, 해시, 검토 결정과 규칙 판정을 담았습니다. 실제 요청·산출물·원본 영수증은 로컬 실행 저장소에 보존했습니다.
