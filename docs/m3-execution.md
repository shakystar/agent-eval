# M3 실행 어댑터

`execute EXPERIMENT TASK CONDITION REPEAT`는 등록된 실험의 한 반복을 실행하고, 산출물을 기존 평가 저장소에 등록한다. `evaluate`, `semantic-grade`, `report`는 저장 증거를 읽는다. M3 예제의 규칙 채점은 공지문 산출물의 존재 여부를 검사한다. 내용 정확성은 별도의 의미 평가 또는 사람 판정 대상이다.

## Linux에서 예제 실행

저장소 루트에서 실행한다. 고정 M0 이미지와 이를 기반으로 한 M2 이미지, 이 버전의 role-runtime·role-orchestrator 소스가 필요하다. 빌더는 기본으로 인접한 두 체크아웃을 사용하며 경로는 `--runtime`, `--orchestrator`로 지정한다. 최초 설치 방법은 [Linux 이미지](../containers/linux/README.md)와 [M2 실행 환경](m2-calibration.md)에 있다.

```sh
python3 containers/linux/build_m3.py
mkdir -p artifacts/m3-demo
docker run --rm --network none --entrypoint sh \
  -v "$PWD/artifacts/m3-demo:/work" agent-eval-m3:dev -ec '
  p=/opt/src/role-orchestrator/.venv/bin/python
  ae() { python /opt/agent-eval-m3/entrypoint.py --store /work/store "$@"; }
  "$p" -m examples.m3.create_example /work/input
  ae bundle /work/input/bundle.json
  ae experiment /work/input/experiment.json
  for condition in solo team material fault; do
    for repeat in 1 2; do
      ae execute notice-m3-fixture notice "$condition" "$repeat"
    done
  done
  ae evaluate \
    notice-m3-fixture rules-1 --reviewer operator --reason initial
  ae report notice-m3-fixture rules-1 --output /work/report
'
```

컨테이너 실행 사용자(UID 1000)가 마운트 경로에 쓸 수 있어야 한다. 결과는 `artifacts/m3-demo/report/report.json`에서 조건과 반복별로 확인한다. 이미 등록한 반복을 다시 요청하면 같은 실행 기록을 반환한다. 보고서를 추가로 내보낼 때에는 새 출력 디렉터리를 지정한다.

리뷰 수정본의 재현 소스는 role-runtime `9ca52f26cddf428149f7a99e7bd754038c2de59c`와 role-orchestrator `72261711b4f8b9eb4216a9ff4be51791c588d360`이다.

## 특정 codex-adapter 커밋으로 빌드

기본 빌드는 role-runtime의 `go.mod`에 지정된 어댑터를 사용한다. 어댑터의 커밋을 따로 검증하려면 로컬 Git 저장소와 커밋 SHA 전체를 함께 전달한다.

```sh
adapter_sha=2b8c204b0cb7e3c63c60a3fa7923e4e9ca4d02bb
tag=agent-eval-m3:adapter-pin
python3 containers/linux/build_m3.py --adapter ../codex-adapter \
  --adapter-commit "$adapter_sha" --tag "$tag"

docker image inspect "$tag" --format '{{json .Config.Labels}}'
docker run --rm --network=none --entrypoint go "$tag" \
  version -m /opt/src/role-runtime/bin/runtime-bridge
```

`--adapter-commit`은 40자리 소문자 SHA-1을 받는다. HEAD의 위치와 무관하게 지정한 커밋에서 `git archive`로 어댑터를 추출한다. 미커밋 파일과 추적되지 않는 파일은 어댑터 빌드 입력에서 제외한다. agent-eval, role-runtime, role-orchestrator는 기존과 같이 지정한 작업 트리를 사용하므로 네 저장소를 함께 재현할 때는 이 세 트리의 버전과 로컬 변경도 확인해야 한다.

최종 이미지의 `org.agent-eval.codex-adapter.commit`과 `org.agent-eval.codex-adapter.archive-sha256` 라벨에 각각 커밋과 tar의 SHA-256이 있다. Docker 빌드는 tar 해시, tar에 기록된 커밋, Go 모듈 이름을 확인한다. 컴파일한 브리지의 `go version -m`에서 `github.com/shakystar/codex-adapter` 바로 다음 줄이 `=> /tmp/pinned-codex-adapter/<전체 SHA> (devel)`인 경우에만 고정 빌드를 완료한다. 이 경로는 빌드 단계의 경로다. 확인 실패 시 기본 모듈로 전환하지 않는다. [표준 빌더 검증 기록](validation/m3-adapter-pin.md)

## 실행 경계

| 계층 | 책임 |
| --- | --- |
| agent-eval CLI·계약 | 과제·조건·반복 확인, 평가 전용 자료를 제외한 실행 입력 생성, 미지원 설정 사전 거부 |
| agent-eval 실행 어댑터 | 입력·산출물·시도 원장, 증거 등록, 복구 관찰 및 평가 버전 보존 |
| role-orchestrator의 Python `Runtime` | 고정 작성·검토 흐름과 주입, 전송 프레임 검사, Go 프로세스 관리 |
| role-runtime의 Go `runtime-bridge` | 실제 작업 제출, 역할별 세션, advisory 프로필, 시도 ID 기반 읽기 전용 영수증 조회 |
| codex-adapter | 기존 Codex 계정·모델 설정으로 실제 턴 수행, 실행 실패 정보 제공 |

`workflow.backend`는 `fixture` 또는 `codex`다. 단독 조건은 작성 단계 하나를 갖는다. 협업 조건은 작성자의 문서를 검토자에게 전달한다. 검토 결과 `revise`이고 수정 예산이 1일 때만 작성자에게 검토 의견을 전달하고 최종 검토를 한 번 수행한다. `accept`, `defer`, 한도 소진 시의 `revise`도 저장한다. 검토자의 판단과 채점기의 과제 판정을 각각 조회할 수 있다.

단계별로 조건당 하나의 주입을 지정할 수 있다. `material`은 지정된 단계의 요청에 추가 자료를 넣고 전후 입력 해시와 적용 횟수를 기록한다. `tool_failure`는 오케스트레이터의 `read_handoff` 호출에서 일시적 오류를 한 번 발생시킨 후 동일한 산출물 해시로 다시 읽는다. 적용 전 중단, 적용, 적용 여부 불확실을 구별한다. 모델 내부 도구 제어, 명시적 모델 변경, 임의 스킬, 강제 예산은 bridge v1의 지원 범위를 벗어난다.

## 실모델과 복구

실제 실행에는 role-orchestrator Python 환경, Go bridge, 로그인한 Codex CLI가 필요하다. 위 예제 생성기에 `--backend codex`를 주고 실험 ID로 `notice-m3-codex`를 사용한다. CLI가 PATH에 없으면 `execute`에 `--bridge /path/to/runtime-bridge --codex /path/to/codex`를 전달한다. Linux 로그인 파일과 바이너리 마운트 예시는 [Linux 실제 Codex 검증](../containers/linux/README.md)에 있다. 모델·인증·도구 프로필은 기존 runtime 경로를 따르며 M2 채점 모델은 따로 설정한다.

Linux에서 `workspace_routing_timeout`이 발생한 경우에는 현재 DNS 응답과 주소별 HTTPS 연결을 먼저 대조한다. 이번 검증에서는 응답이 확인된 주소를 한 컨테이너에만 `--add-host="chatgpt.com:${IP}"`로 적용했다. 동일 컨테이너에서 계정 조회를 확인한 뒤 계획된 반복을 실행했다. [주소별 대조와 실모델 검증 결과](validation/m3.md)

반복마다 새 runtime ID와 디렉터리를 부여하고, 한 반복 안에서는 역할별 세션과 공유 인계 작업공간을 사용한다. 실행 저장소는 단계 제출 전에 의도를 기록한다. 재시작하면 runtime 영수증의 입력·역할과 wire 요청의 시도 ID를 연결해 복구한다. 제출 여부를 확정할 증거가 없으면 `uncertain`으로 보존한다. 동일 반복을 재조회해도 모델 요청을 다시 보내지 않는다. CLI 종료 코드는 완료 0, 실패·중단·불확실 1, 입력·환경 오류 2다.

원본 영수증과 산출물은 로컬 저장소에 보존한다. `report.json`의 반복별 `workflow`에는 단계 상태, 검토 결정, 주입 횟수와 복구 결과가 들어간다. 경과 시간은 복구 대기를 포함하며 bridge가 제공하지 않는 토큰·비용은 미측정이다. [검증 결과](validation/m3.md)

## 늦게 도착한 영수증 대조

`reconcile EXPERIMENT TASK CONDITION REPEAT --bridge PATH`는 Go의 `--inspect-attempt`로 이전 시도를 조회한다. Codex 설치나 인증 없이 실행할 수 있다. 영수증이 아직 없으면 `uncertain`을 유지한다. 작업이 끝났으면 새 관찰을 원장에 추가하고, 협업의 다음 단계가 미제출이면 `prepared`로 반환한다. 이후 명시적으로 `execute`하면 같은 실행 바인딩에서 미제출 단계부터 이어간다. `uncertain` 슬롯에 대한 `execute`도 첫 호출에서는 대조만 수행한다. 기존 실행 환경의 바인딩이 달라진 경우 읽기 전용 대조가 가능하다. 이미 외부 증거를 가져온 슬롯은 제출 전에 거부한다.

규칙 평가는 평가 당시의 실행 관찰을 고정한다. 늦게 관찰된 산출물은 새 평가 ID로 채점한다. 기존 평가와 원본 실행이 보존된다. Docker 기본 진입점은 `execute`와 `reconcile`에 오케스트레이터 환경을 사용하고 채점 명령에는 Inspect 환경을 사용한다.
