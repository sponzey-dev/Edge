# 제품 구성과 재사용 자원

이 문서는 [계획 목표](../plans/plan.md)를 위한 시스템 구성·재사용 판단을 소유한다.
상세 layer/port/runtime 규칙은 [기존 architecture](../../docs/architecture.md),
[AGENTS.md](../../AGENTS.md)와 [ADRs](../../docs/adr/)를 따른다. 새 기술을 선정한 문서가 아니다.

## 서비스와 기술 역할

트래픽은 client → mio HTTP/HTTPS listener → route·availability·upstream transport → backend로
흐른다. 운영 변경은 선택형 static Admin UI 또는 API client → versioned Admin API →
application validation/preparation → bounded Core command/ack → revision/audit로 흐른다.
Blocking file/network preparation과 evidence 수집은 mio 요청 경로 밖에서 수행한다.

| 소유 경계 | 현재 역할 | 계획에서 보존할 점 |
| --- | --- | --- |
| `edge-domain`, `edge-application`, `edge-ports` | 순수 정책·use case·외부 경계 | OS/framework/env에 의존하지 않는 정책과 fake-port 검증 |
| `edge-core` | mio readiness·연결·transport·timeout·backpressure·command 처리 | 명시적 상태 전이, bounded queue, exact payload cleanup |
| `edge-adapters` | rustls·file store·crypto·audit·metrics·maintenance I/O | TLS parsing·파일·비밀정보를 바깥 경계에 유지 |
| `edge-admin-api`, `apps/edge-proxy` | HTTP/API adapter, bootstrap·wiring·운영 CLI | 인증·CSRF, bootstrap-only env, runtime 직접 변경 금지 |
| `apps/admin-web` | HTML/CSS/JS API client | UI 없이 동작 가능, same-origin API와 표시 전용 fallback 구분 |
| `packaging/compose`, `packaging/systemd` | 설치·검증된 offline upgrade/recovery | 고정 경로·tag/digest·journal, 검증 전 기존 실행본 보존 |
| `tests/performance`, `tests/memory-harness` | 분리된 부하·측정·증거 도구 | 제품 policy나 dependency로 들어가지 않음 |

사용자가 확정한 `main`의 모듈 분리를 재사용한다. 문서 작업도 `main`으로 이전했다.
G01은 이 기준에서 후보 버전과 증거 계약을 고정하며, 이전 소스에서 완료한 작업을 다시 만들지 않는다.

## 리소스 재사용 판단

다음은 저장소 정의를 읽은 결과이며 현재 컨테이너·host의 실행 상태를 확인한 inventory는 아니다.
실제 실행 전에는 자원 소유·사용 중인 데이터·version·port·권한을 읽기 전용으로 확인한다.

| 자원·실행 대상 | 소유와 버전 기준 | 재사용·갱신 판단 | 목표 |
| --- | --- | --- | --- |
| `docker-compose.test.yml`의 `edge-test` | 프로젝트 source-test 서비스, Cargo cache named volumes | 기존 서비스를 재사용. Cache나 운영 volume을 일괄 초기화하지 않음 | G01~G03 |
| 같은 Compose의 `performance` profile | `edge-perf`, pinned Node upstream, 별도 pinned k6 | profile/runner 재사용. Runner의 전용 fixture 재구성은 허용된 test scope 내에서만 수행 | G02, G06 |
| 같은 Compose의 `nextcloud-e2e` profile | `main`의 pinned Nextcloud·Edge, `edge-nextcloud-state`·`nextcloud-e2e-html` | 기존 profile·영속 volume을 반복 사용. 별도 Compose·대체 영속 volume을 매번 만들지 않음 | G03 |
| 외부 Linux reference host | ignored `.env`의 기존 host 선택 정보 | 가용성·native amd64·systemd PID 1·Docker 확인 후 재사용. 자격증명과 실제 주소를 계획/evidence에 복사하지 않음 | G05, G06 |
| 기존 macOS reference diagnostic 환경 | 과거 Phase 011의 reference 검증 경계 | 기존 canonical gate가 요구하는 reference 측정용. macOS 제품 운영 지원으로 확대하지 않음 | G06 |
| release archive·OCI image | candidate tag/commit/archive checksum/SBOM/OCI digest | G04에서 동일 identity 검증. Runtime matrix는 발행 artifact를 사용 | G04~G07 |
| installed binary·runtime image manifest | systemd/Compose의 고정 current 실행 경로 | 검증된 실행본 하나가 current를 가리키도록 전환하고 journal rollback 경로는 보존 | G05 |
| generated PKI·raw evidence | ignored `artifacts/`, 제한된 test layout | 기존 runner의 owner-only 경계를 재사용. 공개 증거에는 비밀정보 없는 metadata·digest·판정만 연결 | G06, G07 |

공유 host에서 부하 측정이 다른 서비스에 영향을 줄 수 있으면 전용 실행 시간/격리 자원을
실행 전에 확보한다. 새 환경이 필요한 경우 기존 자원이 충족하지 못하는 조건과 종료·정리
기준을 해당 목표 기록에 남긴다. 계획 수립 중 리소스 생성·기동·삭제는 하지 않는다.

## 실행 파일 갱신과 보존

공식 실행 대상은 platform/architecture/channel별 current 경로로 식별한다.
파일 수정 시각 대신 source·version·checksum/digest로 최신 검증본을 확인한다.
순서는 식별 → 별도 stage에서 검증 → current 전환 → 실제 참조·readiness 검증 → 불필요한
중복·임시 산출물 정리다. 검증 실패 시 정상 current부터 삭제하지 않는다.

이 기준은 rollback journal이 요구하는 predecessor binary/image·backup, 운영 data·certificate·
trust·audit, immutable public release/tag, 보존 대상 evidence를 중복 실행 파일로 취급하는
정책이 아니다. 기존 제품의 rollback/recovery 계약이 끝나기 전에는 필요한 predecessor를
지우지 않는다. 보존 사유·해소 조건과 정리 결과를 G05/G07 증거에 기록한다.

## source와 artifact의 동일성

현재 performance runner는 clean source에서 로컬 image를 build하고 local image ID를 기록한다.
동일 commit이라는 이유만으로 published OCI digest의 배포판을 측정했다고 간주하지 않는다.
G01에서 source-build 측정과 candidate 측정의 연결 계약을 정하고, G04/G06에서 executable
identity 또는 명시적 pinned-image 실행을 검증한다. 검증되지 않은 결과는 characterization으로 남긴다.

현재 promotion validator는 tag/commit/image와 amd64 Compose/systemd matrix의 passed 상태를
확인하지만 원본 C8·soak·측정 artifact까지 독립 검증하지 않는다. G01/G07에서 이 간극을 닫는다.
새 schema/구현 방식은 여기서 미리 확정하지 않고 기존 도구의 최소 변경을 우선한다.
