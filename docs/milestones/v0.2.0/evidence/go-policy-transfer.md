# Go 정책 적용성 검토

**첫 개정 판정 보류, 세 번째 개정 최종 수락.** 장유나의 첫 검토에 이어 파일 출처와 패키지 검사 증거를 대조했다. 두 번째 개정은 계정 조회 단계에서 종료됐다. 세 번째 개정의 판정은 아래에 기록했다.

| 항목 | 고정값 |
|---|---|
| candidate | `722c9f620a707a8dc42c43a44f3666a3ba4fc87e` |
| path | `internal/control/approved_revision.go` |
| subject_tree | `8f1b8381ad360957e3018d9d7acbda68d8843c68` |
| subject_blob | `521b1c461f6e54377ef767427b8c8780570feb69` |
| subject_sha256 | `8bacfcfaecd5a415045fcc3399bad704af047782bfda868ebe372f322aaeca9c` |
| policy_sha | `9bda89879d1587a74d91aff5d8f9d28c103542f6` |

## 전문 검토 기록

후보 722c9f620a707a8dc42c43a44f3666a3ba4fc87e의 internal/control/approved_revision.go 소스와 정책 SHA 표기는 제공됐지만, 작성자 기록·패치·후보 트리·실행 영수증·로그 해시가 없고 upstream도 비어 있다. 실제 불일치가 확인된 것은 아니며, 소스와 검증 결과가 동일 후보에서 나온 것인지 대조할 수 없어 승인을 보류한다. OWN-01(적용): evaluateApprovedRevision의 조회 분기는 CooperativeReceipt를 읽고 submitApprovedRevision을 호출하지 않는다. 하위 호출까지 포함해 빈 상태에서 작업 생성·쓰기가 없는지, 최초·완료 쓰기와 재조회 책임이 분리되는지 확인할 테스트가 없다. API-01(적용): evaluateApprovedRevision은 요청 구조·작업 ID·해시 형식을 검사하고, readApprovedReview와 approvedRevisionInput은 참조 및 계약을 검사한다. 잘못된 입력의 거절 위치와 거절 전 쓰기·제출 여부를 확인할 공개 진입점 테스트가 없으며, 패치가 없어 호환성 검증의 적용 범위도 미확정이다. SER-01(적용): readApprovedArtifact는 원본 바이트의 SHA-256을 대조하고 approvedRevisionInput은 별도 JSON 입력을 직렬화한다. 비ASCII 기준 벡터의 예상 바이트·해시 및 기존 파일 재읽기 결과가 없다. REC-01(제출 경로에 적용, 조회 전용 분기의 제출 복구에는 비적용): evaluateApprovedRevision에서 영수증 조회와 submitApprovedRevision 호출은 보이지만, 논리 키·영속 의도·불확실 시 보류와 대조 동작은 확인할 수 없다. 동시 호출, 의도 저장 직후 중단, 실행 완료 후 응답 저장 전 중단 각각에서 최종 파일 수와 실제 제출 횟수를 검증한 결과가 없다. READ-01(적용): evaluateApprovedRevision의 조회·제출 분기와 readApprovedReview의 선택적 해시 인자 의미는 코드와 주석에서 추적할 수 있다. 이 발췌에서 필수 가독성 수정은 확인되지 않았으나, 전체 호출부와 오류 전달 경로는 대조하지 못했다. ERR-01(적용): evaluateApprovedRevision은 조회 시 not_found만 허용하고 기존 작업 불일치는 conflict로 반환한다. 실패 주입 시 빈 결과·입력 오류·실행 실패·실행 불확실이 호출자에게 구분되는지, 재시도 여부와 로그의 작업 ID·원인 범주·민감정보 제외를 확인할 증거가 없다. TEST-01(적용, 성능 검증은 개선 주장 없어 비적용): 공개 진입점과 실제 저장소·프로세스 경계를 거친 동일 검사의 기준 실패 및 후보 통과 결과와 건너뛴 검사 사유가 없다. 장유나는 작성자 기록·패치·트리 및 정책 식별자를 후보 커밋에 연결하고, 누락된 검사의 실행 영수증과 로그 해시를 같은 커밋에 묶은 증거를 확보한 뒤 재대조한다.

## 보완 증거

`go test -count=1 ./internal/control` 실행 결과

```text
ok  	github.com/shakystar/role-runtime/internal/control	0.553s
```

로그 SHA-256은 `394687bbca3cf6ba0341ee569c2bbf82860c6b7fd42c47021f4da2de0e0d9455`이다. 패키지 검사만으로 아래 세부 경로가 모두 검증됐다고 판정할 수 없다. 후속 근거 제공은 런타임 담당, 재대조는 출처 검토 담당이 맡는다.

## 호출자와 재시작 검증

`internal/control/server.go`의 `revisions.check`와 `revisions.approve` 분기는 각각 조회와 승인 진입점을 호출한다. 고정 런타임에서 실제 네이티브 프로세스 재시작과 Python CLI를 거치는 두 사례를 실행했다. 모델 응답은 fixture를 사용했다.

```text
=== RUN   TestPythonApprovalRecoversReceiptAfterNativeRestart
--- PASS: TestPythonApprovalRecoversReceiptAfterNativeRestart (1.79s)
=== RUN   TestPythonApprovalFailedReceiptIsNotReplayed
--- PASS: TestPythonApprovalFailedReceiptIsNotReplayed (1.70s)
PASS
ok  	github.com/shakystar/role-runtime/internal/workflowmodel	3.951s
```

로그 SHA-256은 `cd40428a4f3468d7b6265b9f776f3429f56c6bf160ab583dbbc6a0e5439457ed`이다.

## 세 번째 개정 독립 판정

acl-015 · accept · 영수증 `c7ea71d2bf83fbe423925a4b29934d0dd1eb598908e6c425a7d03f39173ac7e4`

Q4 읽기 전용 정책 적용성 보고서를 수락한다. 제품 결함 수정이나 후보의 출시를 승인하는 판정은 아니다. 후보 722c9f620a707a8dc42c43a44f3666a3ba4fc87e는 internal/control/approved_revision.go의 파일 이력에 기록된 커밋과 일치하며, 이력상 작성자는 shakystar다. 제공된 증거에서 불일치는 확인되지 않았다. 다만 트리·블롭·소스 SHA-256과 로그 해시는 제시값이며, 실행 영수증이 두 테스트 로그를 동일 후보·트리에 연결한다는 근거는 없다. 신규 패치 대조는 범위 밖이다. 제공 로그에는 control 패키지 통과와 네이티브 재시작 후 영수증 복구·실패 영수증 미재실행 테스트 통과가 기록되어 있다.
OWN-01 적용: evaluateApprovedRevision의 check 분기는 CooperativeReceipt 조회로 끝나며 submitApprovedRevision을 호출하지 않는다. 빈 상태에서 작업·제출이 생기지 않는지와 영속 상태의 최초·완료 쓰기 책임은 별도 검증이 필요하다.
API-01 적용: 호출부의 기능 플래그와 evaluateApprovedRevision의 엄격한 파라미터·ID·해시 형식 검증이 제출보다 앞선다. 구버전 입력·저장 상태의 호환성과 잘못된 요청 거절 전 부수 효과가 없는지는 미입증이다.
SER-01 적용: readApprovedArtifact는 원본 바이트의 SHA-256을 대조하고, approvedRevisionInput은 고정 필드의 구조체와 RawMessage로 JSON을 구성한다. 비ASCII 기준 벡터의 예상 바이트·해시와 기존 파일 재읽기 증거가 없다.
REC-01 적용: evaluateApprovedRevision은 task.ID로 영수증을 조회하고 저장된 작업이 다르면 conflict를 반환한다. 재시작 로그 두 건은 복구와 실패 영수증 미재실행을 뒷받침하지만, 동시 호출·의도 저장 직후·실행 완료 후 응답 저장 전 중단을 각각 검증하거나 실제 제출 수와 최종 파일 수를 따로 측정했다는 증거는 없다.
READ-01 적용: checkRevision과 approveRevision은 공통 평가 함수를 사용하고, 주석은 승인 시 작업을 다시 산출하는 이유를 설명한다. 작업 산출·제출 함수 본문이 없어 이름과 실패 흐름을 끝까지 대조할 수 없으며, 조회 오류와 영수증 불일치 분기의 회귀 사례는 제시되지 않았다.
ERR-01 적용: evaluateApprovedRevision은 영수증 not_found를 허용하되 다른 조회 오류를 전달하고, 작업 불일치는 conflict로 구분한다. 실패 주입 시 공개 응답·종료 코드·재시도 여부 및 진단의 논리 작업 ID·원인 범주·민감 입력 제외 여부는 미입증이다.
TEST-01 적용: 재시작 테스트는 네이티브 프로세스·영속 상태·Python CLI 경계를 지난 것으로 보고됐다. 동일 검사의 기준 버전 실패 원인·후보 통과 대조와 건너뛴 검사 목록·사유는 없다. 성능 개선 주장이 없어 성능 전후 측정 요건은 비적용이다.
다음 단계: 장유나는 후보 커밋·트리·블롭과 실행 명령·로그 해시를 연결한 영수증을 확보하고, 위 미입증 항목을 조항별 회귀 벡터 또는 미실행 사유로 기록한다. 재현된 결함이 있을 때만 별도 제품 수정으로 분리한다.

acl-005 · accept · 영수증 `670174459d3830cfe1cac2a9ad12843dbd99f72436a9d0c696d0dcb16561c35e`

고정된 기존 코드에 대한 Q4 정책 적용성 보고서를 수락한다. 7개 조항 모두 적용되지만, 적용 근거가 있다는 것이 개별 회귀 검사를 통과했다는 뜻은 아니다. 후보 커밋은 제공된 파일 이력과 일치한다. 제공 로그에는 control 패키지 검사와 재시작 검사 2건의 통과가 기록돼 있으나, 해당 실행을 후보 트리에 연결하는 영수증은 없다. 아래 반례는 관측된 제품 결함이 아니라 후속 검사의 판정 기준이다.
OWN-01 적용 — evaluateApprovedRevision의 check 분기는 제출하지 않고 CooperativeReceipt를 조회한다. 빈 상태에서 revisions.check 전후 작업·영수증이 늘거나 실제 제출이 1회라도 발생하면 실패다. 작업 산출 경로의 무쓰기와 최초·완료 쓰기의 단일 책임자는 미확인이다.
API-01 적용 — 호출부의 기능 플래그와 evaluateApprovedRevision의 파라미터·ID·해시 검사가 제출보다 앞선다. 잘못된 해시가 invalid_request로 거절돼도 거절 전에 쓰기나 제출이 있었다면 실패다. 구버전 요청·저장 상태의 호환 벡터도 없다.
SER-01 적용 — readApprovedArtifact는 파일 원본 바이트의 SHA-256을 대조하고, approvedRevisionInput은 별도로 구조체와 RawMessage를 직렬화한다. 전자의 해시 일치만으로 후자의 바이트 동일성을 판정할 수 없다. 비ASCII 기준 입력의 예상 직렬화 바이트·해시와 과거 파일 재읽기 검사가 필요하다.
REC-01 적용 — evaluateApprovedRevision은 check 시 task.ID로 조회한 영수증의 작업을 대조한다. 재시작 로그는 영수증 복구와 실패 영수증 미재실행 사례에 한정된다. 거짓 통과 반례: submitApprovedRevision이 연결하는 외부 제출 경계에서 같은 논리 키로 두 번 제출하고 같은 경로에 같은 결과를 남기도록 결함을 주입한다. 최종 파일 1개·내용 동일이어도 실제 제출 2회이면 실패다. 동일 키 동시 호출, 의도 저장 직후 중단, 실행 완료 후 응답 저장 전 중단 각각에서 재시도 전후의 외부 제출 횟수와 최종 파일 수를 독립 계측한 증거는 없다.
READ-01 적용 — checkRevision과 approveRevision은 평가 규칙을 공유하고 주석은 승인 시 작업을 다시 산출하는 이유를 밝힌다. expectedApprovedRevision과 submitApprovedRevision의 본문은 제공되지 않았다. 조회 오류를 not_found처럼 흘려보내는 경우와 저장 작업 불일치에서 conflict를 누락하는 경우를 구별할 분기 검사가 필요하다.
ERR-01 적용 — evaluateApprovedRevision의 check 분기는 not_found를 허용하고 다른 조회 오류는 전달하며 작업 불일치는 conflict로 반환한다. 조회·제출 실패 주입 후 공개 응답이나 종료 코드, 재시도 여부, 진단의 논리 작업 ID·원인 범주 및 민감 입력 제외를 함께 대조한 증거는 없다.
TEST-01 적용 — 제공된 재시작 검사는 Python CLI, 네이티브 프로세스, 영속 상태 경계를 지난 것으로 보고됐다. 같은 검사가 기준 버전에서 의도한 결함으로 실패하고 후보에서 통과했다는 대조와 건너뛴 검사 목록·사유는 없다. 성능 개선 주장이 없어 전후 성능 측정 요건만 비적용이다.
다음 단계: 강이현은 후보 트리·명령·로그 해시를 연결하는 실행 영수증을 확보하고, 위 사례마다 결함 주입 위치·기대값·실측값 또는 미실행 사유를 기록한다. 실제 위반이 재현될 때만 별도 제품 수정 과제로 분리한다. 이번 판정은 출시 승인이 아니다.
