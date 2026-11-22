# 표준 M3 빌더의 codex-adapter 고정 검증

2026-11-22, WSL Ubuntu 22.04의 Linux/amd64 Docker Engine에서 표준 [빌더](../../containers/linux/build_m3.py)와 [Dockerfile](../../containers/linux/Dockerfile.m3)을 사용했다. 각 이미지에서 네트워크를 끄고 실제 Go 브리지와 합성 모델 응답으로 M3 회귀를 실행했다. 인증 정보와 실모델은 사용하지 않았다.

## 입력

| 항목 | 검증한 값 |
| --- | --- |
| agent-eval 실행 코드 | `6db70ed063b2d993670f56408da0493524a02bfa` |
| 빌더 Python / Dockerfile Git blob | `ebcdcad688d893e8fbfbe43f98b4d7566b4c2c64` / `e0f5ba5c11da14961ff0850741fb3358461ece73` |
| role-runtime | `7b2f83702fac83e4004bf7b105a343872e3e53d6` |
| role-orchestrator | `66657b78210fd16697175abec4b1807e95ed1a28` |
| 기반 이미지 `agent-eval-m2:dev` | `sha256:1d517bc86d8d0a22cd188ad8f1d0c0c6f899e97d1b29b988c1c64484a9c4ccfc` |

## 이미지별 결과

| 모드 | 어댑터 소스 | 최종 이미지 ID | `runtime-bridge` 바이너리 SHA-256 |
| --- | --- | --- | --- |
| 어댑터 옵션 생략 | go.mod의 `v0.0.0-20261119053648-3ab5b920bf6c` | `sha256:76d5691be0f4e9ad27210ecde8a46c0c3778c4b81143c53c17f30a8f020c2eb4` | `1190d3eec04c45ecf232e5d3e14bf32b1278c93d69b28a9ac8f3b672bf598805` |
| 현재 커밋 지정 | `2b8c204b0cb7e3c63c60a3fa7923e4e9ca4d02bb` | `sha256:753bd2eb391cca53cbc8418c28caec1fdc1ba775596701ec18a45b49a06bbcf7` | `1a5c66d6bdb99f0ebf1846b5fe5a00e0cae2e92923bca452f75815fc0e9fa7e3` |
| 같은 체크아웃에서 과거 커밋 지정 | `3ab5b920bf6cf6f0ebaec320068a1cd9652670d8` | `sha256:8ab9326c5512b7e145e0351a4dcbfaa41ef16ca72cf2e6c4cd079966949018a3` | `24082a814e4f50591c11ec43ad58cdede13552b8f31135c51a967d8625905291` |

기본 이미지에서는 `go version -m`에 기존 모듈 버전과 Go 모듈 체크섬이 표시됐고 로컬 교체와 어댑터 고정 라벨은 없었다. 두 고정 이미지에서는 같은 명령으로 실제 의존 모듈에 연결된 교체 경로에서 각각 지정한 전체 SHA를 확인했다. 이미지의 커밋 라벨도 일치했다. 독립적으로 다시 생성한 Git tar의 SHA-256과 이미지 라벨은 각각 다음 값으로 일치했다.

- `2b8c204`의 tar는 `16d50171bc48b802e13cd14993ff9cb0e50b5ce97450671869987fd5f61f1857`이었다.
- `3ab5b92`의 tar는 `f765a5baaad5141298abd4768b7fa5016aeeff7580355b24cf94dfd7c357a3d9`였다.

세 이미지 모두 `runtime-bridge --capabilities`가 `bridge`, `fixture_text`, `inspect_attempt` 버전 1을 반환했다. 각 이미지에서 `test_m3.py` 15개가 모두 통과했다(총 45회, 건너뜀 없음). 첫 기본 모드 점검에서 빈 Docker ARG가 미정의 변수로 처리돼 실패한 뒤 기본값을 명시하고 다시 검증했다.

## 재현과 실패 검사

[빌드 방법](../m3-execution.md)에 따라 이미지를 준비하고 저장소 루트에서 실행한다. 두 번째 명령의 `$tag`에는 검증할 이미지 태그 또는 ID를 지정한다.

```sh
python3 -m unittest discover -s containers/linux -p test_build_m3.py
docker run --rm --network=none --entrypoint /opt/src/role-orchestrator/.venv/bin/python \
  "$tag" -m unittest discover -s tests -p test_m3.py
```

호스트 단위 검사는 임시 Git 저장소에서 두 커밋을 번갈아 선택하고, 로컬 수정·추적되지 않는 파일이 tar에 들어가지 않는지 검사한다. 트리 객체를 커밋으로 전달하는 경우도 거부했다.

| 실패 입력 | 관찰 결과 |
| --- | --- |
| 짧은 SHA, 저장소 경로만 전달, SHA만 전달 | 인수 검사에서 각각 종료 코드 2 |
| 존재하지 않는 전체 SHA, 커밋이 아닌 트리 SHA | Docker 호출 전에 각각 종료 코드 1 |
| 유효한 tar를 유지하고 Docker에 전달하는 커밋만 다른 유효한 SHA로 교체 | tar에 기록된 커밋과 달라 Docker 빌드 실패 |
| 유효한 tar를 유지하고 Docker에 전달하는 SHA-256만 0으로 교체 | `sha256sum -c`에서 실패하고 Docker 빌드 중단 |

이 검증은 선택한 코드를 실제 브리지에 연결했는지와 합성 작업에서의 회귀를 다룬다. 실모델의 응답 품질·비용·가용성은 측정하지 않았다.
