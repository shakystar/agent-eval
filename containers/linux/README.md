# 고정 Linux 검증 환경

Windows에서는 WSL2의 Docker Engine으로 실행합니다. Linux 컨테이너가 Unix socket·파일 잠금·SQLite 상태를 소유합니다. Windows 네이티브 workflow 지원은 아닙니다.

## 빌드

Python 3.12+, Git, Linux Docker가 필요합니다. 아래는 Linux/WSL shell 기준입니다. 저장소 루트에서 실행합니다. clone 대상 디렉터리는 새 경로여야 합니다.

```sh
mkdir -p ../ae-sources
git clone https://github.com/shakystar/role-runtime.git ../ae-sources/role-runtime
git clone https://github.com/shakystar/role-orchestrator.git ../ae-sources/role-orchestrator
git clone https://github.com/UKGovernmentBEIS/inspect_ai.git ../ae-sources/inspect
python3 containers/linux/prepare_context.py --context ../ae-linux-context \
  --role-runtime ../ae-sources/role-runtime \
  --role-orchestrator ../ae-sources/role-orchestrator --inspect ../ae-sources/inspect
docker build -t agent-eval-linux:m0 ../ae-linux-context
IMAGE=$(docker image inspect agent-eval-linux:m0 --format '{{.Id}}')
```

`sources.json`의 정확한 commit만 복제합니다. 원본 checkout의 미커밋 수정은 포함하지 않습니다. 기존 context가 dirty이거나 commit이 다르면 중단합니다. 인증 정보는 build context에 넣지 않습니다. 베이스 이미지 digest와 의존성 버전을 고정했지만 바이트 단위 동일 이미지 재빌드를 보장하지는 않습니다. 실행에는 해당 빌드의 image ID를 사용합니다.

## 합성 검증

```sh
mkdir -p ../ae-results-fixture
docker run --rm --network none \
  --mount type=bind,source="$(realpath ../ae-results-fixture)",target=/results \
  --env AGENT_EVAL_IMAGE_ID="$IMAGE" "$IMAGE"
```

출력 디렉터리는 컨테이너 UID 1000이 쓸 수 있어야 합니다. Go vet/race, 기존 acceptance 19개, 실제 runtime·orchestrator·Inspect 통합을 검사합니다. 실패 시 nonzero로 종료합니다. fixture 원본 상태는 일회성 컨테이너 안에 있으며 요약 JSON만 외부에 보존합니다.

## 실제 Codex 검증

기존 로그인된 Codex의 Linux 네이티브 바이너리 경로를 `CODEX_BIN`, 인증 파일 경로를 `CODEX_AUTH`, 설정 파일 경로를 `CODEX_CONFIG`에 지정합니다. npm JS wrapper를 바이너리로 지정하지 않습니다. UID 1000에서 파일을 읽을 수 있어야 합니다. 기존 인증·모델·네트워크 설정을 그대로 사용합니다.

```sh
docker volume create agent-eval-live
docker run --rm --user root --network none --entrypoint /bin/chown \
  --mount type=volume,source=agent-eval-live,target=/state "$IMAGE" 1000:1000 /state
mkdir -p ../ae-results-live-001
docker run --rm \
  --mount type=volume,source=agent-eval-live,target=/state \
  --mount type=bind,source="$(realpath ../ae-results-live-001)",target=/results \
  --mount type=bind,source="$CODEX_BIN",target=/opt/codex-bin,readonly \
  --mount type=bind,source="$CODEX_AUTH",target=/home/evaluator/.codex/auth.json,readonly \
  --mount type=bind,source="$CODEX_CONFIG",target=/home/evaluator/.codex/config.toml,readonly \
  --env AGENT_EVAL_IMAGE_ID="$IMAGE" "$IMAGE" --mode codex --state /state/live-001
```

실제 모델 호출이 발생합니다. 실행마다 새 state 및 결과 디렉터리를 사용합니다. 기존 state는 덮어쓰지 않으며 실패·불확실 작업을 자동 재실행하지 않습니다. 모델 실행 중 임의 timeout으로 재시도하지 않습니다. 원문·receipt·Inspect 로그는 volume에 남고, 외부 결과 디렉터리에는 요약만 기록됩니다.

Inspect는 별도 Python 환경에서 저장된 산출물만 검사합니다. 재채점 및 runtime 재시작 뒤 receipt·attempt·model-status 불변성을 검증합니다. 고정 작성→검토 과제의 통합 검사이며, 임의 과제 주입이나 의미 품질 검증은 아닙니다.

[실제 검증 결과와 최초 인증 실패 이력](../../docs/validation/m0-linux.md)을 함께 보존합니다.
