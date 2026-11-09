# Current Implementation State

검토일: 2026-11-09. 이 문서는 로컬 Git 소스·기준 문서·테스트 정의를 대조한 현황이다.
이번 문서 정리에서 제품을 실행하거나 전체 테스트·성능 측정·배포 검증을 새로 수행하지 않았다.
과거 문서의 합격 기록은 아래에 별도 표시하며, 현재 소스의 신규 합격으로 간주하지 않는다.

## 제품 정의와 문서 역할

프로젝트 목적·사용자·장기 방향·현재 제품 범위는 [README](../README.md)와
[한국어 README](../README.ko.md)가 정의한다. 목표는 작은 MVP에 머무르는 것이 아니라,
설정 변경·장애 진단·복구를 통제할 수 있는 신뢰할 만한 self-hosted edge gateway다.
현재 집중 범위는 수동 인증서/private PKI를 사용하는 Linux amd64 단일 노드 제품화다.

이 문서는 구현과 검증 상태를 설명한다. Architecture·config·API·보안·운영의 상세 계약은
각 전용 문서를 따른다. 프로젝트 목표·단계·완료 기준은
[프로젝트 계획](../.docs/plans/plan.md)이 소유하고 [문서 지도](../.docs/README.md)에서 연결한다.
로컬 `.tasks/plan.md`는 개발 실행 계획이며 Git에서 제외되어 있다.
과거 단계별 task 기록이나 검증 artifact가 모든 checkout 또는 배포 패키지에 포함된다고
가정하지 않는다.

## 확인한 소스 기준

| 기준 | 로컬 확인 결과 | 해석 |
| --- | --- | --- |
| 작업 checkout·계획 기준 | `main`, `abc7f95` | 2026-11-09 사용자 결정. 작성 중인 문서를 보존하여 실제 작업 브랜치도 `main`으로 전환 |
| 실행 패키지 | `apps/edge-proxy/Cargo.toml`, version `0.1.9` | 이후 후보의 tag와 일치하도록 변경·검증해야 함 |
| 로컬 `v0.1.10` tag | `abc7f95` | Tag 존재를 확인. 해당 소스의 package version은 `0.1.9` |
| 릴리스 metadata 계약 | Tag 버전과 package version의 정확한 일치를 요구 | `v0.1.10`은 `RELEASE_VERSION_MISMATCH` 조건에 해당 |

활성 제품 문서와 프로젝트 계획의 소스 기준은 모두 `main`이다.
이전 브랜치의 문서 편집은 `main`의 운영·릴리스 계약을 보존해 통합했다. Tag는 이동하지 않았다.
원격 GitHub Actions 결과, registry 가용성, release promotion은 이번에 조회하지 않았다.
따라서 tag/commit/push와 배포판 발행, clean-host 검증, 정식 제품 승격은 각각 구분한다.
기존 tag를 옮기거나 과거 검증을 새 identity로 바꾸는 것은 해결 방법으로 간주하지 않는다.

## 소스에 구현된 제품 기능

다음 표의 공통 기능은 현재 checkout의 production 구성과 관련 테스트에서 확인했다.
구현·회귀 테스트 존재를 현재 실행 성공이나 전체 지원 환경의 합격으로 표현하지 않는다.

| 영역 | 구현 범위 | 상세 계약 |
| --- | --- | --- |
| Data plane | 단일 mio HTTP/1.1·HTTPS runtime, Host/exact/prefix routing, HTTP→HTTPS redirect, forwarded/hop-by-hop header 처리, chunked response, timeout·backpressure, WebSocket tunnel | [Architecture](architecture.md), [config schema](config-schema.md) |
| Upstream 가용성 | 다중 upstream, deterministic round-robin, active HTTP/HTTPS health, passive transport ejection, generation-fenced drain, 조건부 GET/HEAD 1회 retry, 502/503/504 오류 구분 | [Failure-aware routing](failure-aware-routing.md), [upstream health](upstream-health-architecture.md) |
| TLS·신뢰 | 수동/file-backed certificate, SNI 선택, 신규 연결 대상 hot install, managed Root trust를 쓰는 strict upstream HTTPS, required inbound mTLS | [Private PKI](private-pki-testing.md), [ADR 009](adr/009-private-pki-bidirectional-trust.md) |
| 설정 lifecycle | parse→normalize→validate→diff→plan→acknowledged apply→revision commit→audit, immutable generation activation, rollback·실패 보상 | [Config schema](config-schema.md), [Admin API](admin-api.md) |
| 관리 | 최초 setup, login/logout, session·CSRF, Proxy Host CRUD, config·certificate/trust 관리, health·log·metric·audit 조회, API client인 선택형 static UI | [Admin API](admin-api.md), [headless 운영](admin-curl.md) |
| 관측·자원 | Product/Field Debug/Development 로그, bounded nonblocking log/metric/health queue, loopback Prometheus, Admin resource summary, connection·logical payload admission | [Observability](observability.md), [resource baseline](memory-resource-baseline.md) |
| Audit | process-wide file-backed typed ledger, intent-before-effect, startup 검증·reconciliation, bounded query, 손상 시 persistent mutation fail-closed | [ADR 010](adr/010-durable-audit-ledger.md), [threat model](threat-model.md) |
| 복구 | age 암호화 offline backup·verify, fresh restore, journal 기반 replace/recovery, schema v3 trust/audit 보존과 v1/v2 read/restore 호환 | [Backup/restore](backup-restore.md), [deployment](deployment.md) |
| 운영 패키징 | Compose·systemd helper, journal 기반 offline upgrade/rollback, loopback live/ready probe, bounded SIGTERM drain, authenticated/CSRF-protected fixed-path support bundle | [Install](install.md), [deployment](deployment.md), [troubleshooting](troubleshooting.md) |

### 반드시 유지할 운영 계약

- Core는 UI 없이 동작한다. UI는 `/api/v1` client이며 runtime table이나 config file을
  직접 수정하지 않는다. Layered/Clean Architecture·Tidy First·TDD 규칙은
  [AGENTS.md](../AGENTS.md)가 소유한다.
- 환경 변수는 bootstrap에서 한 번 읽고 typed argument/dependency로 전달한다.
  실행 중 변경은 validation/apply 경로를 통한다.
- File parser는 지원 필드를 제한한 TOML-like subset이며 완전한 TOML parser가 아니다.
  Unknown field는 validator가 거부한다.
- `config/current` revision pointer가 startup의 기준이다. 비어 있는 repository만
  primary TOML을 seed로 가져오며, 손상된 pointer를 seed fallback으로 숨기지 않는다.
- Config·inbound/outbound TLS·health는 준비된 generation을 bounded command/ack로 활성화한다.
  실패 시 기존 runtime truth와 revision을 보존한다. Listener policy·resource limit의
  restart-required 변경은 즉시 적용되는 변경과 구분한다.
- HTTPS upstream의 connect address는 literal IP이고, Root trust·TLS server name·HTTP Host는
  명시한다. OS Root나 plaintext fallback, request-path blocking DNS를 가정하지 않는다.
- Logical payload ledger와 process RSS는 다르다. Payload limit을 전체 process memory의 절대
  상한으로 해석하지 않는다. Cleanup·RSS plateau·ceiling은 실제 workload별로 확인한다.
- Backup은 offline exclusive data lock 아래 수행한다. Session·CSRF·connection·runtime health·
  drain counter·metrics는 일시 상태이며 backup에서 복원하지 않는다.
- Support bundle은 bounded 진단 자료다. Backup을 대체하지 않으며 API/UI에 filesystem path,
  key·secret·header·cookie·body·query를 반환하지 않는다.
- Local audit hash chain은 손상 탐지 수단이다. 악의적 host 관리자에 대한 위변조 불가능성이나
  부인 방지를 보장하지 않는다.

### 현재 main의 안정화와 검증 도구

검토한 `main`에는 plaintext HTTP/1.1 순차 keep-alive, close/half-close·timeout 처리 보완,
module 분리와 mutation/fuzz regression, source-quality/architecture/index/dependency audit gate,
portable Linux archive, OCI version/revision identity 검증과 candidate promotion validator가 있다.
이 구현을 재사용하며 모듈 분리나 기존 안정화를 미구현 기능으로 다시 계획하지 않는다.

재사용하는 `docker-compose.test.yml`의 `nextcloud-e2e` profile과
`tests/integration/nextcloud/`도 현재 소스에 있다. Edge를 통한 Nextcloud loopback 접속,
영속 volume과 `127.0.0.1:18080` redirect 설정을 포함한다.
기존 대화의 접속/로그 확인은 현재 문서 검토에서 새로 수행한 로그인 E2E가 아니다.
현재 `verify.mjs`는 루트의 HEAD 302/Location만 확인한다. 실제 로그인·세션·파일 요청은
그 검사만으로 검증되었다고 볼 수 없어 프로젝트 목표 G03에서 보완한다.

## 검증 상태와 증거의 한계

### 현재 사용할 수 있는 검증 경계

- Rust workspace에 domain/application/adapter와 실제 mio/rustls 회귀 테스트가 있다.
  `tests/integration/`의 이름만으로 전체 제품 E2E를 의미하지 않으며 실제 테스트 내용을 본다.
- 현재 checkout의 `docker-compose.test.yml`은 상시 `edge-test`와 분리된 performance profile을
  제공한다. `edge-perf` production image → Node.js upstream 경로에 별도 k6가 부하를 보낸다.
  부하 생성은 upstream 앱과 분리되어 있다.
- `tests/performance/`는 smoke·baseline·stress·30분 soak와 host-side CPU/memory sample,
  fail-closed artifact audit를 제공한다. 결과는 ignored `artifacts/performance/`에 보관한다.
- 현재 checkout의 performance workflow는 contract와 짧은 smoke를 자동 실행하도록 정의되어 있다.
  긴 profile의 정의나 CI 파일의 존재만으로 실제 통과를 주장하지 않는다.
- 현재 소스에는 source-quality gate, 동일 host/source identity 비교와 C8 regression comparator,
  clean-host release evidence를 검사하는 별도 promotion workflow가 있다.
  다만 validator의 `passed` 상태 검사가 원본 성능·soak 증거 검증을 대신하지는 않는다.

기존 실행 안내는 [testing guide](testing.md), [release gate](release-gate.md),
[release evidence template](release-evidence-template.md)에 보존한다.
현재 `scripts/`의 memory helper와 `tools/release/`의 architecture/source-index 검사를 재사용한다.
삭제된 과거 helper와 현재 파일을 구분하고, 역사적 script 이름만으로 실행 가능하다고 간주하지 않는다.
Source quality workflow는 `python3 tools/release/check_architecture.py --workspace .`와
`cargo audit`을 포함한다. Performance runner의 기본 local build는 characterization이며,
공개 후보 측정은 명시적 digest와 실행 이미지 확인이 필요하다. 실제 후보의 C8/soak
원본과 clean-host 검증은 후속 목표에서 확보해야 한다.

### 보존하는 과거 checkpoint

아래는 기존 문서의 승인 기록이다. 이번 작업에서는 ignored raw artifact를 재검증하지 않았다.
이 기록을 현재 변경된 tree 또는 새 release의 승격 증거로 재사용하지 않는다.

| Checkpoint | 기록된 결과와 source identity | 추적 위치 |
| --- | --- | --- |
| Phase 010, 2026-07-16 | Durable audit·backup v3 완료. `source-tree-sha256:000b23c310bae98a40e7689139fab45e09300d83d4daee42bc51763d825c1a85` | `artifacts/release-evidence/phase010-20260716-final-r2`, [completion audit](mvp-completion-audit.md) |
| Phase 011, 2026-07-20 | macOS arm64/native Linux x86_64 각각 10 jobs·12 scenarios, ready=true·blocker 0. `source-tree-sha256:2c2bcbf580ed60fe18c330340236ecccf0936d7e5a2d18822e1c36f0fb970862` | [Memory contract](memory-resource-baseline.md), [completion audit](mvp-completion-audit.md) |
| Phase 011 soak·diagnostic | 7,200초·121 observations, churn 60,000·WebSocket lifecycle 7,680, correctness/cleanup failure 0; macOS diagnostic definite leak 0건/0 bytes | 아래 artifact 목록·binding |
| v0.1.9 후보, main의 2026-09-07 기록 | `e1eedc4`의 Ubuntu 22.04 amd64 Compose/systemd upgrade·explicit rollback·보존, C8 baseline, 30분 soak 기록 | 해당 `main` source의 현황 문서와 로컬 실행 계획. 현재 tree나 v0.1.10의 합격을 뜻하지 않음 |

### 과거 release identity와 제한

다음은 이전 main 문서에 기록된 이력이며 이번 검토에서 GitHub 또는 원본 artifact를 다시
조회한 결과가 아니다. 과거 tag를 이동하거나 이 기록만으로 새 후보를 승격하지 않는다.

| Tag | 당시 상태 | Commit | Workflow | 알려진 제한 또는 검증 범위 |
| --- | --- | --- | --- | --- |
| `v0.1.0` | `non-releasable` | — | — | package version 불일치로 발행 전 거부됨 |
| `v0.1.8` | `not-promotable` | — | — | systemd upgrade에서 stop/readiness/startup 문제가 발견됨 |
| `v0.1.9` | `prerelease` | `e1eedc4` | `34082549484` | 소스·artifact 생성과 아래 amd64 upgrade 경로가 기록됨. 제품 승격을 뜻하지 않음 |

`v0.1.9`의 기존 기록은 `v0.1.3→v0.1.9` systemd upgrade와
`v0.0.9→v0.1.9` Compose upgrade 및 각각의 rollback을 다룬다. 이후 기존 task252는 해당
archive의 support bundle 생성 실패를 발견했으므로 이 과거 upgrade 기록을 전체 제품 검증으로
해석하지 않는다.

Phase 011의 상세 artifact root는 다음과 같다.

- `artifacts/memory-evidence/task073-full-linux-x86_64-r1`
- `artifacts/memory-evidence/task073-full-macos-arm64-r1`
- `artifacts/memory-evidence/task073-diagnostic-soak-macos-arm64-r1`
- `artifacts/memory-evidence/task073-macos-leaks-arm64-r1`
- `artifacts/memory-evidence/task073-phase011-memory-release-macos-arm64-r1`

기록된 readiness digest는 Linux
`73cb85a4759b952969320651337106a854dc101c2c146e6f7f0468915a085f66`, macOS
`79162c859929ace3c7d82828639d0a71b3948624ba4c54fb108ee476409853d4`다.
Soak peak RSS는 9,633,792 bytes, first/last median은 9,043,968/9,011,200 bytes다.
Exact nine-file binding digest는
`78d453e0568c069e68c5e563535f2f2497ab42b80d765845a5568bacb7cbcf09`다.
이 값은 명시된 source·OS·architecture·workload에만 적용된다.

### 제품화 완료로 판단하려면 남아 있는 조건

구현 기반과 과거 단계 검증은 있으나 현재 소스 전체를 정식 제품으로 검증 완료했다고
선언할 근거는 이번 검토에서 확인하지 않았다. 남은 조건은 다음과 같다.

- Source branch·package version·tag·archive checksum·SBOM·OCI digest/labels가 같은 후보를
  가리켜야 한다. 현재 확인된 v0.1.10 버전 불일치를 이 상태와 구분해 해결해야 한다.
- 같은 후보 identity에서 source/security gate, Linux amd64 Compose/systemd clean-host
  설치·restart·SIGTERM·upgrade·forced rollback·config/certificate/audit/data 보존을 입증해야 한다.
- 같은 host/config의 baseline 비교, 해당 후보의 soak·resource cleanup, support-bundle 운영
  흐름이 유효한 evidence로 연결되어야 한다. 짧은 performance smoke나 과거 Phase 완료만으로
  이 조건을 충족했다고 보지 않는다.
- 배포 문서·실제 실행 도구·지원 platform 표현이 선택한 소스와 일치해야 한다.
  ARM artifact 생성이나 macOS 개발 테스트를 Linux arm64 공식 운영 지원으로 해석하지 않는다.

이 조건은 [프로젝트 계획](../.docs/plans/plan.md)의 G01~G07에 연결했다.
계획 작성과 문서 통합은 제품 구현·실행 검증·추가 release 완료를 뜻하지 않는다.

## 현재 제공하지 않는 범위

- Let's Encrypt·ACME·HTTP-01/DNS-01·자동 발급/갱신: 사용자가 명시적으로 재개하기 전까지
  신규 작업·설정·외부 검증을 진행하지 않는다. 기존 adapter와 fake ACME/HTTP-01 테스트는
  외부 CA 발급 완료 증거나 운영 지원 경로가 아니다.
- Linux arm64 공식 운영 지원과 native clean-host matrix는 후속 범위다.
  macOS·Windows build artifact도 제품 운영 지원 선언이 아니다.
- HTTP/2·HTTP/3·gRPC·TCP proxy, Kubernetes/discovery, multi-node control, WAF,
  cache/static hosting, weighted/least-connections/sticky balancing, upstream keep-alive pool,
  plugin marketplace는 현재 제품화 범위에 포함하지 않는다.
- Optional/client-identity authorization·revocation, client-certificate outbound mTLS,
  TLS passthrough는 현재 구현 기능이 아니다. 사설 PKI로 테스트할 수 있다는 사실만으로
  다음 개발 대상으로 확정하지 않는다.
- Remote metrics retention·audit export/signing·multi-user RBAC/OIDC, 유료 edition·가격과
  hosted control plane은 이번 정의에서 구현 또는 제공 약속으로 확정하지 않는다.

제품·구현·검증 상태를 분리해 읽기 위해 초기 거대 구상 문서는 README로 통합하고,
비교 조사와 중복된 완료/미완료 진행 서술은 정리한다. 상세 ADR, API/config 계약, 운영 문서와
과거 완료 audit는 각자의 근거를 보존하므로 유지한다.
