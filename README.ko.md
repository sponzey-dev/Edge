# Sponzey Edge Proxy

[English](README.md)

Sponzey Edge Proxy는 웹서비스의 공개·라우팅·장애 대응을 안전하고 이해하기 쉽게 운영하기
위한 self-hosted 리버스 프록시이자 edge gateway입니다. Rust/mio data plane이 트래픽을
처리하고, 선택형 Admin Web UI는 버전이 있는 Admin API를 통해 관리합니다.

## 존재 이유와 주요 사용자

소규모 웹서비스 운영자, Docker Compose 기반 팀, 셀프호스팅 사용자와 여러 도메인·upstream을
관리하는 운영자를 대상으로 합니다. 이들은 프록시 설정을 직접 반복 편집하는 부담을 줄이면서,
설정 변경으로 정상 트래픽을 깨뜨리지 않고 장애 원인을 찾고 운영 상태를 복구할 수 있어야 합니다.

장기 목표는 기능이 늘어나도 설정·관측·복구를 이해하고 통제할 수 있는 예측 가능한 edge gateway입니다.
NGINX의 웹서비스 운영, HAProxy의 가용성, Traefik의 discovery, Caddy의 관리 편의성은 참고하는
방향이며, 이 제품들의 모든 기능을 동일하게 제공하겠다는 약속은 아닙니다.

## 제품 목표와 성공 기준

- UI 또는 동일한 검증 경로의 API로 서비스를 공개·관리하고, UI 없이도 프록시를 운영할 수 있다.
- 잘못된 설정이나 거부된 적용은 동작 중인 runtime을 보존하고, revision과 rollback으로

  변경 이력을 추적하고 되돌릴 수 있다.
- 연결·buffer·timeout·backpressure를 제한하고 실제 workload 검증으로 자원 사용과 장애

  동작을 예측할 수 있다.
- health·로그·metrics·audit·진단 bundle로 credential이나 트래픽 payload를 노출하지 않고

  장애를 확인할 수 있다.
- 식별된 동일 release artifact에서 설치·upgrade·rollback·암호화 복구를 재현하고,

  기능과 성능 검증 근거를 연결할 수 있다.

우선순위는 correctness → safety → operability → simplicity → performance → feature count입니다.
Rust의 메모리 안전성이나 과거 benchmark만으로 운영 검증을 대신하지 않습니다.

현재 집중 범위는 초기 MVP를 넘어선 **신뢰할 수 있는 단일 노드 제품화**입니다.
제품 후보의 대상은 Linux `amd64`의 Docker Compose·systemd 운영입니다. 다른 OS·architecture의
build artifact가 존재해도 운영 지원을 입증하지는 않습니다. 2026-11-09 사용자 결정에 따라
모든 활성 제품 문서와 프로젝트 계획은 `main`의 구현을 기준으로 합니다. 정확한 source identity,
검증 한계와 tag/package version 불일치는 [현재 개발 현황](docs/current-state.md)을 따릅니다.

## 핵심 운영 흐름

1. 고정한 binary/image를 설치하고 보호된 Admin 최초 설정을 완료하거나 headless config/API

   경로로 시작한다.
2. domain/path와 upstream을 정의하고, HTTPS·client 인증이 필요하면 수동 인증서와 관리형

   사설 trust를 준비한다.
3. 변경을 검증하고 검토한 뒤 acknowledged config lifecycle로 적용한다. 적용 실패 시 이전

   상태를 유지한다.
4. health·resource 상태·로그·metrics·audit를 확인하고 필요하면 제한된 support bundle을 만든다.
5. config rollback 또는 offline backup·upgrade·recovery 경로로 복구하고 forwarding과

   Admin 접근을 다시 확인한다.

## 구현된 기능

아래는 소스에 존재하는 기능입니다. 구현과 release 검증 완료는 구분하며,
[현재 개발 현황](docs/current-state.md)에서 구현·과거 checkpoint·남은 제품화 검증을 확인합니다.

### 리버스 프록시와 Routing

- 통합 mio runtime 기반 HTTP/1.1 및 HTTPS 리버스 프록시
- Host, exact path, path-prefix routing
- HTTP에서 HTTPS로 redirect
- `X-Forwarded-*`와 hop-by-hop header 처리
- chunked response, request/response timeout, slow client 처리와 backpressure
- WebSocket upgrade와 양방향 tunnel

### Upstream과 가용성

- service별 단일 또는 다중 upstream
- deterministic round-robin 선택
- active HTTP/HTTPS health check와 passive transport failure ejection
- generation fence가 적용된 administrative drain
- 조건을 만족하는 GET/HEAD 요청의 안전한 1회 retry
- 명시적인 `502`, `503`, `504`와 timeout 처리

### TLS와 사설 신뢰

- rustls TLS termination과 SNI 인증서 선택
- 수동/file-backed 인증서와 신규 연결 대상 certificate hot install
- self-signed 및 Root/Intermediate 사설 PKI 검증
- 관리형 Root trust, 검증된 SNI, 명시적 HTTP Host를 사용하는 엄격한 private upstream HTTPS
- 관리형 client Root trust를 사용하는 required inbound mTLS
- rollback 보상을 포함한 config, TLS, health의 generation 단위 원자적 활성화

현재 인증서 운영 범위는 수동/file-backed 인증서와 사설 PKI입니다. Let's Encrypt, ACME,
HTTP-01/DNS-01, 자동 갱신은 사용자가 명시적으로 재개하기 전까지 보류합니다. 기존 adapter나
test code의 존재를 외부 인증서 자동화가 지원되는 운영 경로라는 의미로 해석하지 않습니다.

### Support bundle

인증된 Admin 사용자는 CSRF 보호가 적용된 Admin UI 또는
`POST /api/v1/support-bundles`로 제한된 진단 bundle을 생성할 수 있습니다. 요청은 경로나
artifact 선택을 받지 않으며 고정 경로의 private tar archive를 만듭니다. API/UI에는 archive ID,
digest, artifact 요약, 누락 항목, 크기만 표시되고 private key, secret, header/cookie/body/query,
filesystem path는 표시되지 않습니다. 이는 backup을 대체하지 않습니다.

### 설정과 관리

- 선언형 TOML config
- parse, normalize, validate, diff, plan, apply, revision commit, audit 흐름
- 실패 시 이전 runtime 상태를 보존하는 안전한 apply와 rollback
- 선택형 same-origin Admin Web UI
- setup, login/logout, CSRF 보호, Proxy Host CRUD, config lifecycle, certificate/trust 관리,

  health, metrics, log, audit 검색을 제공하는 인증된 Admin API
- Admin Web UI가 없는 headless 운영

### 운영과 복구

- Product, Field Debug, Development 로그 모드
- 명시적 pressure/cleanup 회계를 사용하는 process-wide connection 및 in-flight payload admission
- 선택형 loopback 전용 Prometheus metrics와 인증된 Admin metric summary
- 인증된 Admin 검색을 제공하는 bounded, restart-safe, file-backed audit ledger
- 암호화 offline backup, 인증된 verify, fresh restore, replace, rollback과 crash recovery
- backup schema v1/v2 호환과 schema v3 trust/audit 보존
- operational liveness/readiness probe와 제한된 SIGTERM drain
- journal 기반 offline upgrade/recovery helper를 포함한 Docker Compose·systemd 패키징

### 범위 경계와 향후 방향

현재 제품화 범위에서 HTTP/2·HTTP/3·gRPC·TCP proxy·Kubernetes·multi-node control·WAF·
cache/static hosting·고급 balancing·plugin marketplace는 제외합니다. Service discovery,
identity 연동, 추가 protocol과 multi-node 관리는 장기 확장 후보이며 확정된 제공 일정이나
개발 항목은 아닙니다. 확장 시에도 독립적인 data plane과 검증된 config 경계를 유지해야 합니다.

Optional/client-identity mTLS, client certificate를 쓰는 outbound mTLS, TLS passthrough,
remote telemetry/audit 저장과 multi-user RBAC/OIDC는 현재 제공 기능이 아닙니다.
상용 edition·가격·hosted control plane도 확정된 제품 약속이 아닙니다. 현재 소스와 문서에는
아래 MIT 라이선스가 적용됩니다.

## 제공 형태와 기술

운영자가 자신의 host에 설치하는 self-hosted 제품입니다. Static Admin UI는 선택 사항이며
`/api/v1`을 사용합니다. UI/control plane의 분리 배포는 아키텍처 방향이지, 분산 관리 제품이
이미 구현되었다는 의미는 아닙니다.

| 구성 요소         | 현재 구현과 역할                                                              |
| ------------- | ---------------------------------------------------------------------- |
| Proxy runtime | Rust 2021·mio, 명시적 socket/TLS/timeout 상태 머신                            |
| TLS           | Adapter의 rustls, 수동 인증서와 명시적 사설 trust                                  |
| Control plane | Framework-free Rust Admin API와 HTML/CSS/JavaScript UI                  |
| 설정·상태         | Typed TOML config, file-backed revision·certificate/trust/secret store |
| 복구·audit      | age 암호화, tar archive, SHA-256 무결성과 file-backed audit ledger            |
| 패키징           | Binary, Docker/Compose, Linux systemd helper                           |
| 테스트 도구        | Rust workspace/memory harness, Node.js upstream과 분리된 k6 부하 생성기         |

Core hot path는 Tokio 대신 mio를 사용합니다. 외부 adapter의 async dependency는 이 runtime
계약을 바꾸지 않습니다. [아키텍처](docs/architecture.md)와
[의존성 경계](docs/dependencies.md)를 참고하십시오.

## 설치

### 소스에서 빌드

필요 조건:

- Cargo가 포함된 Rust toolchain
- macOS 또는 Linux

Release binary를 빌드합니다.

```bash
cargo build --release -p edge-proxy
```

Binary는 다음 경로에 생성됩니다.

```text
target/release/edge-proxy
```

### Docker Compose

필요 조건:

- Docker
- Docker Compose

공식 release는 SemVer tag와 immutable manifest digest가 함께 지정된 published Linux
image를 사용합니다. 압축을 푼 release package에서 다음을 실행합니다.

```bash
sudo ./compose/install.sh \
  --image-tag vX.Y.Z \
  --image-digest RELEASE_MANIFEST_IMAGE_SHA256_WITHOUT_PREFIX
sudo docker compose --project-directory /etc/sponzey-edge/compose \
  --file /etc/sponzey-edge/compose/docker-compose.yml up -d --wait
```

로컬 source 개발에서만 명시적 override를 사용합니다.

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml --profile local-build up --build
```

Runtime 경로, 권한, backup, 지원 platform 경계, 배포에 관한 자세한 내용은
[`docs/install.md`](docs/install.md)와 [`docs/deployment.md`](docs/deployment.md)를 참고하십시오.

### 재사용 가능한 테스트 컨테이너

테스트 컨테이너를 한 번 시작한 뒤 Cargo dependency와 target cache를 유지하며 반복 사용합니다.

```bash
docker compose -f docker-compose.test.yml up -d --build
docker compose -f docker-compose.test.yml exec edge-test \
  bash -c 'cargo fmt --check && cargo clippy --workspace --all-targets -- -D warnings && cargo test --workspace -- --test-threads=1'
```

테스트 컨테이너는 host port를 공개하지 않고 운영 data나 secret을 mount하지 않습니다. 집중
테스트, 중지·재시작 및 cache 초기화 방법은 [`docs/testing.md`](docs/testing.md)를 참고하십시오.

### 재사용 가능한 Nextcloud 통합 검증

같은 `docker-compose.test.yml`의 `nextcloud-e2e` 프로필은
`nextcloud.test`와 로컬 브라우저 주소인 `localhost`, `127.0.0.1` 요청을 loopback 전용 Edge
listener를 거쳐 Nextcloud로 전달합니다. 최초 한 번만 초기화하고, 이후에는 같은 서비스와 named
volume을 재사용합니다.

```bash
docker compose --profile nextcloud-e2e -f docker-compose.test.yml build edge-nextcloud
docker compose --profile nextcloud-e2e -f docker-compose.test.yml up -d --wait
node tests/integration/nextcloud/verify.mjs
```

포트 변경, 데이터 보존, 명시적 초기화 방법은
[`docs/testing.md`](docs/testing.md#reusable-nextcloud-through-edge-integration)를 참고하세요.

### Release 성능 테스트 환경

지속 Compose 성능 경계는 `edge-test`와 분리됩니다. production `edge-perf` 이미지를 빌드하고,
결정론적 Node.js upstream까지의 경로로 k6 트래픽을 전송합니다. 먼저 기능 gate를 실행합니다.

```bash
node tests/performance/bin/run.mjs smoke
```

runner는 성능 서비스만 재생성하고 ignored test PKI를 만들며 raw 결과를
`artifacts/performance/<run-id>/`에 게시합니다. host에는 읽기 전용 Node dashboard만
`127.0.0.1:3000`으로 공개합니다. Edge Admin은 host port가 없고 컨테이너에 Docker socket을
mount하지 않습니다. 긴 baseline/stress/soak profile은
[`docs/testing.md`](docs/testing.md#release-performance-test-environment)를 먼저 확인하십시오.

## 사용법

### 1. Upstream 준비

샘플 config는 다음 주소에서 HTTP service가 실행 중이라고 가정합니다.

```text
http://127.0.0.1:3000
```

### 2. 샘플 Config 확인

[`examples/minimal.toml`](examples/minimal.toml)은 `0.0.0.0:8080`에서 요청을 받고,
`localhost` Host를 선택해 `3000`번 port의 upstream으로 전달합니다.

```toml
schema_version = 1

[admin]
bind = "127.0.0.1:9443"
enabled = true

[logging]
mode = "product"

[storage]
data_dir = ".sponzey"

[runtime]
max_connections = 1024
max_inflight_payload_bytes = 134217728
upstream_read_timeout_ms = 30000

[[listeners]]
name = "http"
bind = "0.0.0.0:8080"
protocol = "http"

[[services]]
name = "example"

[[services.upstreams]]
url = "http://127.0.0.1:3000"

[[routes]]
name = "example"
hosts = ["localhost"]
paths = ["/"]
service = "example"
```

### 3. 프록시 시작

소스에서 실행합니다.

```bash
SPONZEY_DATA_DIR=.sponzey \
SPONZEY_CONFIG_FILE=examples/minimal.toml \
SPONZEY_ADMIN_BIND=127.0.0.1:9443 \
SPONZEY_LOG_MODE=product \
cargo run -p edge-proxy
```

또는 release binary를 실행합니다.

```bash
SPONZEY_DATA_DIR=.sponzey \
SPONZEY_CONFIG_FILE=examples/minimal.toml \
SPONZEY_ADMIN_BIND=127.0.0.1:9443 \
SPONZEY_LOG_MODE=product \
target/release/edge-proxy
```

환경 변수는 bootstrap 시점에만 읽습니다. 시작 이후에는 Admin Web UI 또는 검증된 Admin API
config lifecycle을 통해 runtime config를 변경합니다.

### 4. Proxy Routing 확인

```bash
curl -i -H 'Host: localhost' http://127.0.0.1:8080/
```

### 5. Admin Web UI 열기

다음 주소를 엽니다.

```text
http://127.0.0.1:9443/
```

새 data directory에서는 최초 Admin setup을 완료하고 로그인합니다. Proxy Hosts 화면에서
domain, path, upstream, health check와 HTTPS policy를 생성하거나 변경합니다. UI는
`/api/v1`을 통해 변경을 적용합니다. `apps/admin-web/index.html`을 직접 열면 프록시를 실제로
제어하지 않습니다.

### 6. Headless Config 적용

Primary config 파일은 비어 있는 revision repository를 위한 최초 seed입니다. Current revision이
생성된 뒤에는 seed 파일을 수정하거나 process 환경 변수를 변경하지 말고 Admin API의 validate,
diff, apply, rollback endpoint를 사용합니다.

Config field와 API 예제는 다음 문서에 있습니다.

- [`docs/config-schema.md`](docs/config-schema.md)
- [`docs/admin-curl.md`](docs/admin-curl.md)
- [`docs/admin-api.md`](docs/admin-api.md)
- [`docs/nginx-migration.md`](docs/nginx-migration.md)

## 문서 안내

목표·순서·의존성·완료 기준은 [문서 지도](.docs/README.md)와
[프로젝트 계획](.docs/plans/plan.md)에서 확인합니다.

| 확인할 내용                   | 기준 문서                                                                                                                       |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| 제품 목적·사용자·방향·범위          | 이 README와 [English README](README.md)                                                                                       |
| 구현·소스 기준·검증 근거·남은 제품화 조건 | [현재 개발 현황](docs/current-state.md)                                                                                           |
| 개발 규칙과 설계 경계             | [AGENTS.md](AGENTS.md), [아키텍처](docs/architecture.md), [ADR](docs/adr/)                                                      |
| 설정과 control-plane 계약     | [Config schema](docs/config-schema.md), [Admin API](docs/admin-api.md), [curl 운영 흐름](docs/admin-curl.md)                    |
| 설치와 운영                   | [설치](docs/install.md), [배포](docs/deployment.md), [backup/restore](docs/backup-restore.md), [장애 대응](docs/troubleshooting.md) |
| 관측과 보안                   | [Observability](docs/observability.md), [threat model](docs/threat-model.md), [private PKI](docs/private-pki-testing.md)    |
| 검증과 release evidence     | [Testing](docs/testing.md), [release gate](docs/release-gate.md), [evidence template](docs/release-evidence-template.md)    |

Phase별 설계·완료 기록은 과거 결정과 검증 근거를 보존합니다. 당시 baseline·script 이름·기능
제안이 현재 범위를 덮어쓰거나 다른 source identity의 release 합격을 의미하지는 않습니다.

## 라이선스

프로젝트 소스와 동봉 문서에는 [MIT 라이선스](LICENSE)가 적용됩니다.
Third-party dependency의 개별 라이선스는 [의존성 문서](docs/dependencies.md)를 참고하십시오.
