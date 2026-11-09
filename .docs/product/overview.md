# 제품 목표와 프로젝트 범위

정의 기준은 [한국어 README](../../README.ko.md)와 [English README](../../README.md)다.
이 문서는 정의를 바꾸지 않고 거시적 목표를 프로젝트 목표 G01~G07에 연결한다.
현재 구현과 과거 검증의 사실 기준은 [current state](../../docs/current-state.md)다.

## 목표 대응

| 제품 목표 ID | README에서 확인한 사용자 결과 | 프로젝트 목표 | 반영 상태 |
| --- | --- | --- | --- |
| P1 | UI/API로 서비스를 관리하고 UI 없이도 프록시를 운영 | [G03](../plans/plan.md#g03-실제-서비스를-관리하고-계속-사용할-수-있다) | 이번 계획에 포함 |
| P2 | 잘못된 변경에서 정상 runtime을 지키고 revision·rollback으로 복구 | [G02](../plans/plan.md#g02-장애와-변경에서도-프록시의-동작과-경계를-보존한다), [G05](../plans/plan.md#g05-배포판으로-설치하고-장애-후-복구할-수-있다) | 기존 구현의 실패·복구 검증을 닫음 |
| P3 | 자원 사용과 부하·장애 동작을 실제 workload에서 예측 | [G02](../plans/plan.md#g02-장애와-변경에서도-프록시의-동작과-경계를-보존한다), [G06](../plans/plan.md#g06-후보의-성능과-자원-사용을-재현하고-판정할-수-있다) | 기존 자원·C8 계약을 재사용 |
| P4 | 민감정보 노출 없이 장애 원인과 운영 변경을 추적 | G03, [G05](../plans/plan.md#g05-배포판으로-설치하고-장애-후-복구할-수-있다), [G07](../plans/plan.md#g07-근거가-확인된-동일-후보를-제품으로-승격한다) | 사용자 흐름·support bundle·audit 증거 연결 |
| P5 | 같은 release에서 설치·upgrade·rollback·암호화 복구를 재현 | [G01](../plans/plan.md#g01-검증할-소스와-버전의-기준을-하나로-만든다), [G04](../plans/plan.md#g04-설치할-후보-배포판의-출처와-내용을-확인할-수-있다), G05~G07 | 이번 계획의 최종 종료 조건 |
| 장기 방향 | 기능이 늘어도 설정·관측·복구를 통제하는 self-hosted edge gateway | G02의 기존 확장 경계 보존 | 장기 기능 자체는 후속 결정 |

위 P1~P5는 README의 제품 목표를 식별하기 위한 이름이다.
세부 완료·실패·검증 기준은 [프로젝트 계획](../plans/plan.md)만 소유한다.

## 이번에 도달할 상태

운영자는 식별된 Linux amd64 배포판을 Compose 또는 systemd로 설치하고, route·수동 인증서·
private trust를 관리하며, 장애를 확인하고 config/upgrade/backup 경로로 복구할 수 있다.
개발자는 기존 public 계약과 mio/port 경계를 보존하면서 재현 가능한 회귀 테스트로 변경한다.
검토자는 그 배포판의 기능·자원·성능·복구 증거를 추적하여 제품 승격 여부를 판단할 수 있다.

단계별 최소 기능은 [capabilities](capabilities.md), 기존 구성과 재사용 자원은
[system](../architecture/system.md), 순서와 종료점은 [plan](../plans/plan.md)을 따른다.

## 범위의 근거

| 항목 | 상태·근거 |
| --- | --- |
| 신뢰할 수 있는 단일 노드 제품 | README와 이전 사용자 결정. 초기 MVP로 목표를 축소하지 않음 |
| Linux amd64, Compose·systemd | 기존 실행 계획·정의에서 확정. 실제 검증한 OS/version을 지원 안내에 명시 |
| Manual/file-backed certificate와 private PKI | 기존 사용자 결정. 인증서 없이 운영하는 제품으로 바꾸는 뜻이 아님 |
| 안정화·속도·동작 보존 리팩터링 | 기존 개발 요청과 계획을 재사용. 새 기능에 필요한 경계만 정리 |
| Node 성능 upstream·별도 부하 생성·지속 Compose | 기존 사용자 결정. 매번 새로운 Compose나 영속 volume을 만들지 않음 |
| Nextcloud 실제 동작 검증 | 기존 사용자 요청. 현재 소스의 HEAD redirect 검사와 로그인·파일 흐름 검증은 구분 |
| 일정·새 버전 번호·지원 SLA | 미확정. 임의의 출시일·수치·지속 지원 약속을 만들지 않음 |
| 실행 소스 기준 | 2026-11-09 사용자 결정으로 `main` 확정. 작성 중인 문서를 보존해 작업 브랜치도 전환함 |

## 이번 계획 밖의 방향

| 방향 | 분류와 이유 |
| --- | --- |
| Let's Encrypt·ACME·HTTP-01/DNS-01·자동 갱신 | 명시적 보류. 사용자가 재개하기 전까지 착수·외부 검증하지 않음 |
| Linux arm64 운영 지원·native matrix | 합의된 후속 범위. artifact를 없애거나 지원으로 표시하지 않음 |
| Discovery·identity·추가 protocol·multi-node | 장기 후보. 단일 노드 운영 결과를 얻는 데 필요하지 않음 |
| WAF·cache/static hosting·고급 balancing·plugin marketplace | 현재 제품화에서 제외. 기능 수를 늘리는 목표로 추가하지 않음 |
| Optional/client-identity mTLS·outbound mTLS·TLS passthrough | 미구현 확장 후보. 현재 private-PKI 기능의 검증과 구분 |
| Remote metrics/audit·RBAC/OIDC | 후속 검토. 현재 관측·audit·관리 흐름을 먼저 검증 |
| 상용 edition·가격·hosted control plane | 미확정. MIT인 현재 프로젝트의 제품 약속을 임의로 변경하지 않음 |

G01~G07이 끝나면 이번 단일 노드 제품화 계획은 종료한다. 장기 방향은 새 사용자 요구와
별도 범위 결정이 있을 때 다음 계획으로 연결하며, 이번 완료 조건에 계속 덧붙이지 않는다.
