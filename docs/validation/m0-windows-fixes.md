# M0 Windows 오류 수정

2026-11-20. 기존 실패 기록을 보존하고 별도 결과를 추가했습니다.

## Inspect 로그 버퍼

원인은 SQLite에 전달한 Windows 경로 길이였습니다. 실제 버퍼 DB 경로는 284자였으며 부모 디렉터리가 존재해도 일반 경로 연결이 실패했습니다. 같은 파일을 `\\?\` 확장 경로로 열면 성공했습니다. 권한이나 인증 오류로 처리하지 않았습니다.

고정 Inspect commit `ec5d110b1704a6eb31e2efedec59a12190df80e1`에 [로컬 패치](../../experiments/m0/patches/inspect-windows-buffer-path.patch)를 적용했습니다. Windows의 buffer 디렉터리만 확장 경로로 정규화하며 저장 위치는 유지합니다. 읽기 전용 URI는 `?`, `#`, 공백, 한글을 인코딩하고 `mode=ro`를 유지합니다. UNC 경로와 이미 확장된 경로도 처리합니다. 다른 OS의 경로 처리는 유지합니다.

수정 소스를 가상환경에 다시 설치한 후 다음을 확인했습니다.

- [경로 회귀 검사](../../experiments/m0/test_windows_log_paths.py) 4개 통과. 긴 경로 쓰기·읽기, 읽기 전용 쓰기 거부, 없는 DB 미생성, prefix 처리를 확인했습니다. UNC 네트워크 연결을 시험한 것은 아닙니다.
- [native 실행 결과](m0-windows-native-results.json): `eval()` 성공, solver 1회, 로그 읽기와 append 재채점 성공. 추가 solver 호출과 외부 모델 호출은 0회입니다.
- [사후 평가 회귀](m0-windows-posthoc-results.json): M0 계약 검사 통과.
- `pip check`: 통과.

설치 버전은 `0.3.292.dev17+gec5d110b1.d20261119`입니다. 날짜 suffix는 빌드 시스템의 로컬 수정 표기이며 공식 upstream release가 아닙니다. [manifest](m0-windows-fix-manifest.json)에 패치와 실제 설치 모듈의 SHA-256을 기록했습니다. Inspect upstream에는 PR·커밋을 전송하지 않았습니다. 제어 소켓의 Windows 지원이나 외부 모델 실행은 이번 성공으로 입증하지 않습니다.

재현은 새 Inspect checkout에서 지정 commit을 선택한 후 patch를 적용하고 동일 가상환경에 설치합니다. `--no-deps`는 M0 의존성이 이미 설치된 환경에서 사용합니다.

```text
git -C ../inspect checkout ec5d110b1704a6eb31e2efedec59a12190df80e1
git -C ../inspect apply ../agent-eval/experiments/m0/patches/inspect-windows-buffer-path.patch
python -m pip install --no-deps ../inspect
python -m unittest discover -s experiments/m0 -p test_windows_log_paths.py -v
python experiments/m0/native_eval_probe.py --report artifacts/native-eval-results.json
```

Windows의 pip 임시 경로가 긴 환경에서는 앞선 M0 설치와 같이 해당 설치 프로세스의 TEMP/TMP를 짧은 작업 디렉터리로 지정합니다. 전역 보안·권한·인증 설정은 변경하지 않았습니다. 기존 명세의 사후 평가 기본 경로는 유지합니다.

## workflow Windows 빌드

원인은 control server가 `syscall.Flock`, `LOCK_EX`, `LOCK_NB`를 모든 OS에서 컴파일했기 때문입니다. [수정 패치](../../experiments/m0/patches/role-runtime-windows-build.patch)는 OS별 잠금 구현을 분리합니다. Linux/macOS의 배타 잠금은 유지하며 다른 OS에서는 잠금 없이 실행하지 않고 명확한 미지원 오류를 반환합니다.

role-runtime의 로컬 `fix/m0-windows-control-build` branch에 커밋했습니다. 정확한 commit과 원본 commit은 [manifest](m0-windows-fix-manifest.json)에 기록했습니다. 해당 저장소의 원격 branch는 변경하지 않았으며 적용 가능한 전체 diff를 agent-eval에 보존했습니다.

Go 1.26.11에서 Windows workflow 빌드, 관련 vet, 미지원 OS 오류 검사와 race 검사가 통과했습니다. Linux/amd64·Darwin/amd64 테스트 바이너리도 교차 컴파일했지만 실행하지는 않았습니다. 생성한 Windows 바이너리를 실제 기동하면 `state store currently supports Linux/macOS only`로 종료합니다.

**컴파일 오류는 해결됐으며, Windows workflow 실행 지원은 추가하지 않았습니다.** state store, Unix socket·권한, Python orchestrator의 `fcntl`을 포함한 전체 Windows 이식은 별도 범위입니다. Linux/macOS의 잠금 배타성·해제 회귀 검사 실행도 남습니다.
