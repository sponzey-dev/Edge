# 프로젝트 문서 지도

작성일: 2026-11-09. 제품 정의 → 목표 대응 → 프로젝트 계획 → 기능·설계·운영 계약 순서로 읽는다.
이 문서 모음은 계획과 기준 위치를 연결한다. 구현 완료나 실제 검증 통과 기록을 대신하지 않는다.

## 처음 읽는 순서

1. [프로젝트 정의](../README.ko.md): 누구의 어떤 운영 문제를 해결하는지, 현재 범위와 장기 방향.
2. [작업 규칙](../AGENTS.md): 아키텍처·TDD·설정·로그·검증·리소스 관리 규칙.
3. [목표 대응](product/overview.md): 거시적 목표와 G01~G07의 연결, 범위와 결정 상태.
4. [프로젝트 계획](plans/plan.md): 단계별 결과·의존성·종료 기준·검증.
5. [현재 개발 현황](../docs/current-state.md): 소스별 구현 상태와 과거 증거의 유효 범위.

## 사실별 기준 위치

| 확인할 사실·작업 | 먼저 읽을 문서 | 상세 기준 |
| --- | --- | --- |
| 제품 목적·사용자·성공 방향 | 루트 README | [목표 대응](product/overview.md) |
| 이번 프로젝트의 목표·순서·완료 판정 | [프로젝트 계획](plans/plan.md) | G01~G07 절 |
| 필요한 기능과 구현·검증의 구분 | [기능 대응](product/capabilities.md) | 기존 API/config/보안 계약으로 연결 |
| 구성·의존성·재사용 자원 | [시스템 구성](architecture/system.md) | [기존 아키텍처](../docs/architecture.md)와 ADR |
| 기능 변경 | 해당 목표·기능 대응 | [Config](../docs/config-schema.md), [Admin API](../docs/admin-api.md) |
| 인증·권한·민감정보 변경 | [보안 모델](../docs/threat-model.md) | [Admin API](../docs/admin-api.md), [관측성](../docs/observability.md) |
| 데이터·인증서·복구 변경 | [Backup/restore](../docs/backup-restore.md) | [Private PKI](../docs/private-pki-testing.md), [배포](../docs/deployment.md) |
| 설치·upgrade·장애 대응 | [배포](../docs/deployment.md) | [설치](../docs/install.md), [장애 대응](../docs/troubleshooting.md) |
| 검증·release evidence | [프로젝트 계획](plans/plan.md#검증과-증거-재사용) | [Testing](../docs/testing.md), [release gate](../docs/release-gate.md) |
| 실제 실행 task·진행 기록 | 로컬 `.tasks/plan.md`와 관련 task | Git 제외 대상. 배포되는 프로젝트 계획으로 간주하지 않음 |

상태·필드·오류 코드의 상세 정의는 기존 계약 문서가 소유한다. 이곳에서 같은 명세를 복제하지 않는다.
운영 명령은 선택한 소스에서 실제 도구의 존재와 일치하는지 확인한 뒤 사용한다.

## 기존 위치와 연결 관계

| 기존 자료 | 현재 역할·위치 | 이번 정리 |
| --- | --- | --- |
| 루트 README/README.ko.md | 제품 정의와 사용자 진입점 | 유지, 프로젝트 계획 링크 추가 |
| 기존 `PROJECT.md` | 정의는 README, 목표 대응은 `product/overview.md`, 기능·구성은 각각 대응 문서 | 앞선 정의 작업에서 통합·삭제된 상태 유지 |
| `docs/current-state.md` | 구현·소스 기준·과거 증거 현황 | 유지, 계획과 역할 연결 |
| `docs/architecture.md`, `docs/adr/` | 상세 책임·계약·설계 결정 | 기존 경로 유지, `architecture/system.md`가 구성과 탐색을 안내 |
| `docs/admin-api.md`, `config-schema.md`, 보안·운영 문서 | 상세 계약과 운영 안내 | 기존 경로 유지, 실제 충돌은 실행 기준 정리 목표 G01에서 대조 |
| `.tasks/plan.md` | G01을 구체화한 현재 개발 계획 | 사용자 선택으로 갱신. 기존 task·state·context·phase는 유지 |
| Phase audit와 ignored artifacts | 특정 source/workload의 역사적 근거 | 현황 문서로 연결, 신규 후보의 PASS로 복제하지 않음 |

새 프로젝트 계획의 목표·의존성·완료 기준은 `.docs/plans/plan.md` 한 곳에서 관리한다.
후속 실행 작업은 해당 G-ID를 인용한다. 실행 task의 체크박스와 측정값을 이 문서들에 복제하지 않는다.

2026-11-09 사용자 선택에 따라 로컬 `.tasks/plan.md`는 G01의 D01~D03과 4개 구현 단계를
상세화했다. G02~G07은 상위 프로젝트 계획에 후속으로 유지하며, 기존 미완료 task252의
artifact 검증을 삭제하거나 완료로 바꾸지 않았다. 새 task 생성이나 구현 실행은 하지 않았다.

## 상세화 상태와 남은 결정

현재 계획은 Linux amd64 단일 노드 제품화와 기존 기능의 안정화·성능 회귀 통제에 한정한다.
G01은 바로 검토 가능한 인수 사례를 포함한다. G02~G07은 선행 결과가 나오면 해당 목표의
필수 실패·경계 사례를 상세화하며, 전체 미래 명세의 완성을 착수 조건으로 삼지 않는다.

실행 소스 기준은 사용자 선택에 따라 `main`으로 확정했고 실제 작업 브랜치도 전환했다.
새 버전 번호, 실제 실행 host의 가용성, 외부 발행 시점은 아직 확정하지 않았다.
자세한 상태와 의존성은 [계획의 결정 항목](plans/plan.md#결정과-착수-조건)을 따른다.
