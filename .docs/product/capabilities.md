# 목표별 최소 기능과 계약 연결

제품 목표의 기준은 [overview](overview.md), 단계·완료·검증 기준의 기준은
[project plan](../plans/plan.md)이다. 아래 상태는 소스·검증 도구의 존재를 뜻하며 PASS 기록이 아니다.

| 기능 ID | 필요한 사용자·검토 결과 | 목표 | 현황과 최소 보완 | 계약·명세 위치 |
| --- | --- | --- | --- | --- |
| C01 | 어느 소스·버전을 설치·측정하는지 혼동하지 않음 | G01, G04 | `main` 기준 확정, metadata validator 존재. v0.1.10/package 0.1.9 불일치와 후보 identity를 실행 기준에서 해소 | [현재 소스](../../docs/current-state.md#확인한-소스-기준), plan G01 인수 사례 |
| C02 | 정상·악의적·느린 요청과 upstream 장애에서 명시적 결과와 cleanup | G02 | HTTP/HTTPS·framing·retry·health·drain·WebSocket 구현. 실패 회귀를 재사용하고 누락만 보완 | [Architecture](../../docs/architecture.md), [routing](../../docs/failure-aware-routing.md), [config](../../docs/config-schema.md) |
| C03 | UI/API/headless 운영과 설정 실패 후 이전 서비스 유지 | G03 | Admin/auth/config·TLS trust 관리 구현. 같은 use case의 실제 사용자 흐름 증거 필요 | [Admin API](../../docs/admin-api.md), [curl](../../docs/admin-curl.md), [private PKI](../../docs/private-pki-testing.md) |
| C04 | Nextcloud를 같은 테스트 환경에서 로그인·재접속·파일 요청까지 사용 | G03 | 기존 profile·volume을 재사용하여 로그인·세션·작은 파일·업로드 제한·재시작을 소스 개발 환경에서 검증 | `docker-compose.test.yml`, `tests/integration/nextcloud/`, [테스트 안내](../../docs/testing.md) |
| C05 | 한 release의 binary/image를 식별하고 설치·upgrade·rollback | G04, G05 | archive/SBOM/OCI·Compose/systemd·journal helper 구현. 동일 후보의 발행·clean-host evidence 필요 | [Install](../../docs/install.md), [deployment](../../docs/deployment.md), [evidence template](../../docs/release-evidence-template.md) |
| C06 | 장애 진단과 data/certificate/trust/audit 복구 | G03, G05 | 로그·metrics·audit·support bundle·암호화 backup 구현. 실제 운영/실패/복구 흐름 연결 | [Observability](../../docs/observability.md), [backup](../../docs/backup-restore.md), [threat model](../../docs/threat-model.md) |
| C07 | 성능 저하·누수·자원 압력을 정해진 조건에서 판정 | G06 | Node/k6·RSS harness·C8 존재. 현재 runner의 로컬 build 결과와 발행 후보 artifact의 연결을 검증해야 함 | [Testing](../../docs/testing.md), [resource baseline](../../docs/memory-resource-baseline.md), [ADR 011](../../docs/adr/011-quantitative-memory-resource-safety.md) |
| C08 | 미실행·위조·다른 후보의 증거로 제품 승격되지 않음 | G01, G07 | `main` promotion validator는 identity·matrix·passed 상태를 검사. C8/soak와 원본 artifact 검증 연결은 불충분 | plan G01의 증거 계약 인수 사례, G07 |

## 동작 보존 정리의 범위

`main`은 이미 parsing/framing·transport·resource·queue·health·bootstrap 경계를 상당 부분
분리했다. 이를 새 구현으로 다시 세지 않는다. `edge-core/src/lib.rs`의 남은 runtime 조합과
Admin adapter의 변경이 필요할 때만 관련 책임을 작은 단위로 추출한다.
줄 수나 파일 수 자체를 목표로 삼지 않으며 port 경계·public 출력·상태 전이·성능을 보존한다.
확장성을 이유로 미사용 plugin API, 새 runtime, 새 저장소나 범용 framework를 추가하지 않는다.

## 명세 상세화 순서

- 다음 작업인 C01/C08의 검토 입력·기대 결과·거절 사례는 [plan G01](../plans/plan.md#g01-검증할-소스와-버전의-기준을-하나로-만든다)에 준비되어 있다.
- C02~C07은 선행 검증에서 실제 누락이 확인된 부분만 인수 사례를 상세화한다.
- 기존 API/config schema·보안 규칙은 새 기능 목록으로 재정의하지 않는다.
  변경이 불가피하면 원래 계약 문서·regression·사용자 흐름을 함께 갱신한다.
- 이후 실행 task는 G-ID와 C-ID를 연결한다. 이 문서에 실행 task 체크박스나 결과를 복제하지 않는다.
