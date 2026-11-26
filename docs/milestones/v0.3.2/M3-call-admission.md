# M3 배정별 호출 원장과 채점 적격성

현행과 후보 모두 `agent_eval.m3_assignment`로 실행한다. 실험 디렉터리 아래에 비교군·사례·반복 번호로 고유한 슬롯을 만든다. 같은 슬롯의 재실행은 실행 전에 중단한다. 계획된 복구나 새 표본을 추가할 때 슬롯 이름을 바꿔 기존 배정의 재시도를 최초 실행으로 집계하면 안 된다.

오케스트레이터가 네이티브 run ID와 attempt ID를 발급한 뒤, 기록기가 배정 계획에서 두 값을 읽는다. 기록기는 공식 app-server로 전달하기 직전 각 `turn/start`의 순서와 요청 바이트 해시를 슬롯 원장에 남긴다. 응답을 받으면 그 행을 실제 턴 ID와 연결한다. 기록 범위는 app-server로 향하는 로컬 전송 시도다. 전달 전에 기록하므로 기록 직후 프로세스가 종료되면 상대가 실제로 수신했는지는 미확인이다.

| 관측 | 채점 결과 |
|---|---|
| 배정된 시도의 시작 1건, 일치하는 응답과 검증된 완료 영수증 | accept · 채점 가능 |
| 시작 응답 유실, 불완전한 기록, 다른 배정의 원장, 쓰기 진행 중 | hold · 채점 보류 |
| 같은 배정에서 시작 2건 이상 | reject · 채점 제외 |

원장 디렉터리는 실험 실행자가 소유한다. 채점 시 실행을 종료한 슬롯의 원장과 네이티브 상태를 함께 보관한다. 해시는 요청 식별과 원본 대조에 쓰며 기록기의 신원 서명이나 제공자 내부 재시도·과금까지 보증하지 않는다.

## 실행과 재검증

오케스트레이터와 평가 패키지를 같은 Python 환경에서 읽을 수 있게 설정한다. 프로젝트의 고정된 명부 경로·개정과 절대 경로의 브리지 및 Codex 실행 파일을 사용한다. 양쪽 비교군은 같은 평가 명령을 쓰며, 승인한 역할 계약 개정은 외부 실험 계획에서 각각 고정한다.

```sh
python -m agent_eval.m3_assignment --root "$experiment" --arm current \
  --case "$case_id" --repeat 1 --backend-executable "$codex_binary" -- \
  --lab "$lab" --revision "$roster_revision" --member "$member" --task "$task" \
  --runtime "$bridge" --profile "$profile" < "$input"
python -m agent_eval.m3_score --root "$experiment" --arm current \
  --case "$case_id" --repeat 1 --bridge "$bridge"
```

두 번째 명령은 기존 슬롯의 채점 적격성을 다시 조회한다. 정상은 종료 코드 0, 증거 부족은 3, 중복 전달은 4다. 실험 표본에서 보류와 거부를 최초 배정 분모에 유지한다.

오프라인 인수 시험은 다음 명령으로 재현한다. 빈 출력 경로를 주고 고정된 오케스트레이터 소스를 PYTHONPATH에 포함한다. 합성 서버 원장은 기록기 원장과 별도로 실제 수신한 요청을 확인한다.

```sh
python docs/milestones/v0.3.2/reproduction/call-boundary/admission.py \
  --lab "$lab" --bridge "$bridge" --output "$new_directory"
```
