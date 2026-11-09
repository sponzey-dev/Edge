# Admin web assets

| Path | Responsibility | Boundary / side effects |
| --- | --- | --- |
| `app.js` | Admin UI state, authenticated API client, and operational rendering. | Uses versioned Admin API only; CSRF is memory-only and reload requires login; support bundle uses fixed server paths and displays only secret-free receipt facts. Session behavior is tested in `tests/integration/admin-web-session.test.mjs`. |
| `index.html` | Static Admin console structure. | Contains no runtime configuration or filesystem paths. |
