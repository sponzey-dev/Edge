# Sponzey Edge 단일 노드 제품화 프로젝트 계획

작성일: 2026-11-09. 소스 기준: 사용자 확정 `main` (`abc7f95`에서 시작).
상태: 프로젝트 계획 수립. 아래 목표의 구현·실행 검증은 **NOT RUN**이며 기존 task 상태를 초기화하지 않는다.

## 목표와 종료점

[README의 제품 목표](../../README.ko.md#제품-목표와-성공-기준)를 달성하기 위해 운영자가
Linux amd64 배포판을 설치하고 서비스를 관리·진단·복구할 수 있으며, 검토자가 같은 후보의
기능·성능·자원·복구 증거를 확인해 제품으로 승격할 수 있는 상태에 도달한다.
목표 대응은 [overview](../product/overview.md), 필요한 최소 기능은
[capabilities](../product/capabilities.md), 재사용 자원은 [system](../architecture/system.md)에 연결한다.

G01~G07을 충족하면 이번 계획은 종료한다. 새 기능·platform·상용 정책을 완료 조건에 계속
추가하지 않는다. 이후 확장은 별도 계획으로 결정한다. 일정·새 release 번호는 미확정이다.

## 범위와 기준

- 포함: 기존 HTTP/1.1/mio·WebSocket·수동 TLS/private PKI·routing/health/retry/drain,
  config apply/rollback·Admin/auth·로그/metrics/audit·support bundle·암호화 복구,
  Compose/systemd 제품 운영, 필요한 동작 보존 모듈화와 회귀·성능 검증.
- 공식 운영 지원 대상: Linux amd64. 검증한 OS/version·환경은 evidence와 지원 문서에 구체적으로 남긴다.
- 기존 macOS reference 측정은 자원 검증용이며 macOS 제품 운영 지원으로 확대하지 않는다.
- 제외: 인증서 자동화, Linux arm64 운영 지원, HTTP/2·HTTP/3·gRPC·TCP, Kubernetes/discovery,
  multi-node, WAF, cache/static hosting, 고급 balancing, plugin marketplace, 새 상용 edition.
- Let's Encrypt·ACME·HTTP-01/DNS-01·자동 갱신은 사용자 명시 재개 전까지 착수하지 않는다.
- 기존 API v1/error·config/revision·backup v1~v3·수동 인증서/private trust 계약을 보존한다.
  새 기능 없이도 목표를 달성할 수 있으면 기능을 추가하지 않는다.

## 현재 출발점과 계획 근거

사실 기준은 [current state](../../docs/current-state.md)다. 소스와 테스트 정의를 읽은 결과이며,
이번 계획 작업에서 runtime·성능·원격 Actions·registry를 새로 검증한 결과는 아니다.

| 확인한 사실 | 계획에 미치는 영향 |
| --- | --- |
| `main`은 이전 checkout의 후속 구현을 포함하며 사용자가 기준으로 확정 | 기존 안정화·모듈화·helper를 재사용. 실제 작업 브랜치도 `main`으로 이전 |
| `v0.1.10` tag는 `abc7f95`, executable package version은 `0.1.9` | G01/G04에서 새 후보의 version/tag 정합성을 확보. 기존 tag는 이동하지 않음 |
| `main`에 parser/framer/transport/resource/queue·bootstrap 모듈 분리와 회귀가 이미 있음 | 전체 재작성이나 파일 수 목표를 세우지 않고 G02에서 실제 누락만 보완 |
| Nextcloud `verify.mjs`는 HEAD 302/Location만 확인 | 로그인·세션·실제 파일 흐름은 G03에서 별도 검증 |
| Performance runner는 clean checkout의 로컬 production image를 build하고 local image ID를 기록 | G01/G04/G06에서 published candidate와의 동일성 계약을 먼저 준비 |
| Promotion validator는 identity·matrix와 passed 상태를 검사하나 C8/soak 원본을 검증하지 않음 | G01에서 증거 계약을 정하고 G07에서 누락·변조·다른 후보 증거의 승격을 차단 |
| 과거 Phase 010/011과 v0.1.9 검증 기록이 존재 | 계약·절차·참조값은 재사용하되 변경된 후보의 PASS로 복사하지 않음 |

## 단계와 의존성

| 단계 | 목표 | 이전 단계에서 가져올 것 | 다음 단계 진입 조건 |
| --- | --- | --- | --- |
| S0 기준 고정 | G01 | `main` 소스·정의·기존 계약 | 소스/버전·증거·검증 범위의 모순과 미확정 의존성이 식별되고 착수 계약 준비 |
| S1 기능·안정성 | G02, G03 | G01의 baseline·인수 사례 | 기존 동작과 실제 사용자 흐름의 필수 source 검증 PASS |
| S2 후보 배포판 | G04 | G02/G03의 검증된 source, tag 전 metadata | 동일 identity의 발행 archive·image와 검증 가능한 receipt 확보 |
| S3 운영·부하 검증 | G05, G06 | G04의 immutable candidate와 준비된 host/fixture | 각 필수 clean-host·복구·C8·memory/soak evidence PASS |
| S4 제품 승격 | G07 | G01~G06의 같은 후보 증거 | 독립 검증·지원 안내 일치·사용자 발행/승격 지시에 따라 동일 후보 제품화 |

G02/G03, G05/G06은 각각 선행조건이 충족되는 독립 작업을 병행할 수 있다. 공유 host에서
성능 측정과 파괴적 복구 검증을 동시에 돌려 결과를 오염시키지 않는다.
필수 검증이 FAIL/NOT RUN이면 그 결과에 의존하는 단계는 진입하지 않는다.

## G01 검증할 소스와 버전의 기준을 하나로 만든다

**연결:** P5, C01/C08. **선행:** `main` 선택은 확정. 그 밖의 release 번호·실행 host는 아래 결정 항목 참조.

**결과:** 개발자·운영자·검토자가 동일한 source/계약을 보고 무엇을 검증할지 판단한다.

최소 범위는 현재 문서 변경을 `main`의 최신 계약과 통합하고, version/tag 규칙·지원 platform·
측정 profile·후보 identity·증거 검증 범위를 하나의 기준으로 고정하는 것이다.
이전 후보의 code를 되돌리거나 완료된 모듈화를 반복하지 않는다.
진행 중인 `.tasks/` 상태는 보존하고 후속 실행 작업이 이 계획의 G-ID를 인용하게 한다.

**다음 작업에 필요한 인수 사례:**

| 사례 | 입력·행동 | 기대 결과·보존 상태 | 예정 검증·증거 |
| --- | --- | --- | --- |
| A01 / C01 | 같은 version/package/tag metadata와 명시적 source 입력 | 해당 candidate만 승인; 다른 branch나 현재 작업본을 혼합하지 않음 | metadata contract test·baseline manifest |
| A02 / C01 | v0.1.10/package 0.1.9와 같은 mismatch, 이미 존재하는 tag | 발행 전에 거부. 기존 tag/정상 실행본·runtime data를 바꾸지 않음 | negative contract와 tag 불변 확인 |
| A03 / C08 | 다른 commit/digest·없는 raw artifact·변조된 digest·PASS 문자열만 있는 증거 | 승격에 필요한 증거로 거부; release 상태는 변하지 않음 | fake/temp evidence의 validator regression |
| A04 / C01/C07 | dirty source 또는 local build와 published candidate의 연결 없음 | canonical candidate 성능 결과로 승인하지 않음. 정상 서비스를 건드리지 않음 | runner preflight/identity contract |
| A05 / C01 | 현재 README/API·운영 안내와 source gate 대조 | 삭제 문서 참조·부정확한 지원/자동화 claim이 없고 실제 main 도구와 일치 | documentation/index/architecture contract |

현재 validator가 이미 충족하는 사례는 재사용하고 실패를 확인한 누락만 최소 보완한다.
Schema/runner의 상세 구현은 이 인수 조건을 만족하는 가장 작은 변경으로 결정한다.

**완료:** 실행 baseline과 입력 identity, 검증 도구·원본 evidence의 연결 계약이 준비되고
metadata·문서·누락 증거 거부 회귀가 PASS다. 문서만 만든 상태를 G01 완료로 표시하지 않는다.
**제외:** 실제 부하·host 변경·release 발행. 해당 결과는 다음 목표가 소유한다.

## G02 장애와 변경에서도 프록시의 동작과 경계를 보존한다

**연결:** P2/P3/장기 확장 경계, C02. **선행:** G01의 baseline·검증 계약.

**결과:** 잘못된 요청·끊긴 backend·느린 연결·포화와 config/TLS/health 교체에서 정상 연결과
이전 유효 설정을 보호하고 명시적인 오류·cleanup을 관찰할 수 있다.

최소 범위는 기존 framing/header/length·keep-alive/close/half-close·timeout/backpressure,
retry/drain·TLS/mTLS/WebSocket·command 포화·generation/rollback regression을 대조하고
재현되는 결함과 빠진 중요 경계만 보완하는 것이다. 응답 시작 후 두 번째 오류 응답을 붙이지 않고
한 번의 terminal cleanup으로 connection/payload ownership을 해제해야 한다.

필요한 정리는 관련 runtime/adapter 책임만 characterization으로 고정한 뒤 작은 단위로 추출한다.
Tidy와 behavior 변경을 분리하고 API·config·오류·로그·I/O 순서를 보존한다.
이미 분리한 모듈은 재사용하며, LoC·파일 수 목표나 미사용 범용 추상화는 두지 않는다.

**예정 검증:** pure state/use-case tests, 실제 mio/rustls loopback, malformed/mutation,
slow/reset/포화, 원자적 activation/compensation과 다음 정상 요청의 성공.
Source workspace·architecture/source-index·dependency gate와 변경된 public contract를 검증한다.
**완료:** 해당 실패가 재현 테스트로 설명되고 기대 status/close·이전 revision 보존·최종 cleanup·
복구 요청이 PASS다. 미관측 panic·secret leak·data 손상을 정상 종료로 숨기지 않는다.
성능 영향은 G06에서 최종 판정한다. 새 protocol·balancing·기능 추가는 제외한다.

## G03 실제 서비스를 관리하고 계속 사용할 수 있다

**연결:** P1/P4, C03/C04/C06. **선행:** G01. G02의 관련 변경이 있으면 그 regression PASS.

**결과:** 운영자가 UI 또는 headless API로 route·수동 인증서/private trust를 관리하고,
실제 Nextcloud 서비스를 같은 Compose·영속 volume으로 반복 사용할 수 있다.

기존 `docker-compose.test.yml`의 `nextcloud-e2e`와 main fixture를 재사용한다.
핵심 검증은 loopback 접속 → login 화면·정적 자원 → 로그인 POST → session 유지·재접속 →
현재 proxy body 한도 안의 작은 파일 목록/업로드/다운로드 → restart 후 데이터·정상 접속 보존이다.
Nextcloud가 요구하는 method/header/WebDAV 요청을 실제 흐름으로 확인하며, 한도 초과 요청의
명시적 거부도 확인한다. 이 시험을 Nextcloud 모든 기능·대용량 파일 지원 선언으로 확대하지 않는다.

DNS 미등록 도메인 redirect·404·502가 생기면 요청 시각/ID와 Edge/upstream의 제한된 관측으로
원인을 재현하고 좁게 수정한다. HEAD 302 또는 healthy만으로 로그인 성공을 대신하지 않는다.
기존 502의 원인을 근거 없이 재시작 중 일시 현상으로 확정하지 않는다.

UI/API에서는 setup/login·session/CSRF 거부, route CRUD·validate/diff/apply/rollback,
수동 certificate/trust·health/resource/audit·support bundle을 검증한다.
잘못된 변경은 이전 forwarding을 유지하고 UI fallback은 적용된 runtime으로 보이지 않아야 한다.

**완료:** 브라우저/HTTP 사용자 흐름과 Admin/headless의 정상·거절 결과, restart 보존·로그 masking이
재현 가능한 evidence로 PASS다. 테스트 계정 값·cookie·CSRF·PEM·파일 내용을 증거에 남기지 않는다.
새 Compose, 새로운 운영 계정 체계나 certificate automation은 제외한다.

## G04 설치할 후보 배포판의 출처와 내용을 확인할 수 있다

**연결:** P5, C01/C05. **선행:** G02/G03 PASS, 검토된 source와 사용자 확정 candidate 번호.

**결과:** 운영자가 설치할 archive/image와 측정 대상이 어떤 source인지 독립 확인한다.

Source·문서·lockfile·version을 동결한 뒤 새 immutable candidate를 발행한다.
기존 v0.1.10을 이동하거나 package가 다른 artifact를 같은 tag로 덮어쓰지 않는다.
Source quality 이후 tag/package metadata·static amd64 archive·checksum·SPDX SBOM·OCI
version/revision·anonymous exact-digest pull이 하나의 identity에 맞아야 한다.

**예정 검증:** build/publish contract, archive ELF/runtime compatibility, manifest validator,
실제 digest/label·binary identity 교차 확인. Performance source-build와 published artifact가
연결되지 않으면 candidate 측정에 쓰기 전 G01의 계약에 맞게 최소 runner 경계를 보완한다.
**완료:** 설치 가능한 후보 artifact와 해당 source/내용의 검증 receipt가 존재한다.
Tag/push/publish는 별도 실행 지시에 따라 수행하며, 후보 발행을 제품 승격으로 보고하지 않는다.

## G05 배포판으로 설치하고 장애 후 복구할 수 있다

**연결:** P2/P4/P5, C05/C06. **선행:** G04 candidate, 재사용 host의 가용성·소유/격리 확인.

**결과:** 운영자가 발행 배포판과 안내만으로 설치·진단·upgrade·복구하고 같은 서비스를 되찾는다.

기존 Ubuntu 22.04 amd64 reference 환경을 우선 확인해 Compose와 systemd matrix를 수행한다.
Systemd 검증은 systemd가 PID 1인 host에서 수행하며 container startup으로 대체하지 않는다.
공식 image tag+digest/archive만 사용해 install·forwarding/Admin·live/ready·restart·SIGTERM,
upgrade·강제 실패 rollback·중단 journal recovery·uninstall/cleanup을 검증한다.

Config/revision·manual certificate·trust·secret·audit·사용자 data 보존을 확인하고, encrypted
backup verify → fresh restore/replace → startup → 새 Admin login → trusted HTTPS → audit query/
next append를 연결한다. Wrong passphrase·손상·권한/lock·symlink·ambiguous journal은
이전 정상 data/current를 보존하며 정해진 오류로 거부해야 한다.
Support bundle은 실제 endpoint/UI 흐름과 allowlist·byte/log-age bound·path rejection을 확인한다.

**완료:** Compose/systemd 각각의 정상·실패·보존·복구·정리 evidence가 G04의 같은 identity로 PASS다.
Non-root·loopback Admin·packaging hardening을 확인하고 정상 실행 경로는 검증된 current를 가리킨다.
Rollback 필수 predecessor·backup과 운영 data를 중복 파일로 오인해 삭제하지 않는다.
Host 신규 설치·관련 없는 container/volume 삭제·업무 data로 파괴적 검증하는 범위는 제외한다.

## G06 후보의 성능과 자원 사용을 재현하고 판정할 수 있다

**연결:** P3/P5, C07. **선행:** G04, 기준 host·reference artifact·candidate identity 연결 확보.

**결과:** 개발자와 검토자가 같은 조건에서 throughput/latency·자원 압력·해제·장기 안정성을 판정한다.

기존 Node upstream·별도 k6·CPU/memory sample·audit·RSS harness를 사용한다.
선택된 source의 실제 helper와 canonical 계약을 확인하고, 기존 fixture·profile·한도를 유지한다.

- C8: 같은 host/config/workload에서 각각 audited 3회 baseline. Median RPS는 reference의
  95% 이상, p95/p99는 각각 110% 이하, error rate 증가 없음. 기존 승인 C8 기준을 변경하지 않는다.
- Reference raw artifact가 없으면 이전 승인 source를 같은 조건에서 재측정해 audit한다.
  Candidate 실패를 숨기기 위한 reference 교체·완화는 하지 않는다.
- 기존 stress·30분 soak는 부하 상태·오류·CPU/RSS·cleanup을 확인한다. Canonical 7,200초
  memory/soak를 대신하지 않는다.
- Phase 011의 fixed 12-scenario·ceiling/plateau·exact cleanup·source binding을 재사용한다.
  Native Linux x86_64와 기존 macOS reference profile, 7,200초/121-observation soak·reference
  deep diagnostic을 기존 계약 범위에서 검증한다. Linux arm64 gate는 추가하지 않는다.
- After-load active connections/logical payload 0, normal pressure와 recovery 요청 성공을
  시나리오 기준대로 확인한다. RSS와 logical payload를 혼동하지 않고 ceiling을 임의로 늘리지 않는다.

**완료:** 같은 후보의 원본·sample·summary·digest와 독립 audit/comparator가 PASS이며,
로컬 build 결과가 candidate artifact와 연결되지 않으면 제품 증거로 승인하지 않는다.
독립 실행마다 측정 identity를 남기고 log/credential/PKI 원문을 공개 evidence에 포함하지 않는다.

## G07 근거가 확인된 동일 후보를 제품으로 승격한다

**연결:** P4/P5, C08. **선행:** G01~G06의 필수 결과 모두 PASS.

**결과:** 검토자가 배포판·사용 문서·지원 범위·실제 원본 evidence가 일치함을 확인하고,
사용자 지시에 따라 검증된 동일 candidate를 제품으로 승격한다.

최소 범위는 증거 index의 실제 artifact 참조·digest·source/host/config/profile·결과를 독립 검증하고,
누락·tamper·mixed identity·FAIL/NOT RUN을 거부하는 것이다. 기존 `passed` 문자열과 matrix
객체 존재만으로 C8·soak·복구·support evidence를 승인하지 않는다.
Public README/install/deployment·실행 명령·지원 OS/architecture와 원본 증거를 최종 대조한다.
Evidence index는 비밀정보 없이 검토 가능한 위치에 기록하고 raw private 자료와 분리한다.

**완료:** 사용자가 지시한 발행/승격이 끝나고, 같은 tag/commit/digest의 product release와 지원 안내가
일치하며, 정리된 current 실행 경로·필수 보존 예외·복구 안내가 확인된다.
지시 전에는 `승격 준비 완료`로 구분하고 제품 승격 완료로 보고하지 않는다.
이후 기능 제안은 이번 목표의 미완료 항목으로 편입하지 않는다.

## 검증과 증거 재사용

공통 필수 규칙은 [AGENTS.md](../../AGENTS.md), 실행 안내는
[testing](../../docs/testing.md), 후보 계약은 [release gate](../../docs/release-gate.md)를 따른다.
계획은 검증 예정만 기록하며, 실행 결과는 해당 task/evidence에 기대·실제 결과, PASS/FAIL/NOT RUN,
명령·입력·환경·source/tag/digest·원본 참조·오류·정리 결과를 남긴다.

긴 검증 전에 source·문서·도구·profile을 고정한다. 이후 raw artifact는 ignored 경계에 만들고
결과 수집 중 측정 checkout을 수정하지 않는다. 검토용 evidence index commit은 동결 candidate를
명시적으로 참조하며 그 commit 자체를 측정한 것처럼 표시하지 않는다.

동일 candidate/source·도구·host/config/profile와 원본 digest·독립 판정이 유효하면 결과를
재사용한다. 변경·실패·누락·원본 소실 등 무효화 이유가 있을 때만 영향받은 검증을 재실행한다.
Source identity 계약상 달라진 tree는 같은 후보의 증거로 바꾸지 않으며, release 입력이 변경되면
새 후보로 구분한다. 과거 artifact의 PASS를 현재 후보로 복사하거나 gate를 줄이지 않는다.

## 결정과 착수 조건

| 항목 | 결정 상태·근거 | 언제 해결할 것인가 |
| --- | --- | --- |
| Source·문서 기준 | 사용자 답변으로 `main` 확정, 실제 branch 전환·문서 통합 | 완료된 계획 입력. Git commit/push는 아직 별도 실행하지 않음 |
| Linux amd64·manual/private PKI·재사용 Compose | 기존 정의와 사용자 결정 확정 | 유지 |
| C8와 canonical memory 기준 | 기존 계약 재사용, 수치 완화 없음 | G01에서 선택 source의 도구와 정확히 대조 |
| 다음 candidate 번호 | 미확정. v0.1.10은 이동하지 않음 | G01에서 metadata 준비, G04 발행 전에 사용자 지시로 확정 |
| 실제 Linux/macOS host와 reference artifact | 과거 선택 환경은 존재하나 현재 가용성은 미확인 | G05/G06 착수 전 읽기 전용 inventory와 source-bound artifact 확인 |
| 원본 증거/후보 image 연결 방식 | 현재 도구의 간극 확인, 최소 보완 방식은 미확정 | G01 인수 사례로 정하고 G04/G07 전에 구현·검증 |
| 일정·출시일·SLA | 미확정 | 이번 계획에서 약속하지 않음 |
| Tag/push/publish·제품 승격 | 계획 수립 요청을 실행 권한으로 확대하지 않음 | 각각 해당 실행 요청이 있을 때 기존 지시 범위 안에서 수행 |

바로 다음 착수 대상은 G01이다. Branch 선택을 다시 묻거나 이전 모듈 분리를 반복하지 않고,
현재 main의 metadata·문서 계약과 evidence validator의 누락 거부를 검증 가능한 상태로 닫는다.
실행 task 분해·코드 수정·컨테이너 기동·부하 실행은 이번 프로젝트 계획 작성에 포함하지 않는다.
