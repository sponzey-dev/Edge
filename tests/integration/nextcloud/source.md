# Reusable Nextcloud integration boundary

| Path | Responsibility | Boundary / side effects |
| --- | --- | --- |
| `edge-nextcloud.toml` | Fixed non-secret Edge route from `nextcloud.test`, `localhost`, and `127.0.0.1` to the private Compose Nextcloud address. | Bootstrap-only test configuration; no runtime config mutation. |
| `verify.mjs` | Runs the loopback login surface and authenticated Nextcloud user-flow checks. | Bounded local HTTP requests; preserves a test-owned sentinel file and does not remove Compose resources. Browser and restart validation are separate. |
| `login-surface.mjs` | Checks the login response and required login application script. | Bounded local HTTP requests. |
| `response-validation.mjs` | Validates local redirect and login page shape without exposing response contents. | Pure response checks used by the verifier. |
| `user-flow.mjs` | Checks authenticated session, small WebDAV file, and oversized upload rejection. | Uses test credentials in memory and retains only the identified test sentinel in Nextcloud. |
| `response-validation.test.mjs`, `verify.test.mjs`, `user-flow.test.mjs` | Exercise redirect, login failures, WebDAV use, and failed-upstream detection. | Local fake HTTP server and Node's built-in test runner; do not access persistent data. |
