## 개발 기준과 검증

[공통 개발 정책](https://github.com/shakystar/agent-collaboration-lab/blob/c541f5ba978d06bc0e5ce7a1c1df0dff1166149f/docs/development-policy.md)을 적용한다. 검증 명령은 레포 루트에서 실행한다. 프로젝트 의존성을 설치한 Python 환경에서 `python -m unittest discover -s tests -v`. 선택 의존성 때문에 건너뛴 검사를 결과에 표시한다.
