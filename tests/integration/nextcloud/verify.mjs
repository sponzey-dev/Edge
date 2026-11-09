import { checkLoginSurface } from "./login-surface.mjs";
import { runUserFlow } from "./user-flow.mjs";

const port = process.env.SPONZEY_NEXTCLOUD_EDGE_PORT ?? "18080";
if (!/^\d{1,5}$/.test(port) || Number(port) < 1 || Number(port) > 65535) {
  throw new Error("invalid local Edge port");
}
const origin = `http://127.0.0.1:${port}`;

try {
  await checkLoginSurface(origin);
  const result = await runUserFlow({
    origin,
    username: "test-admin",
    password: process.env.SPONZEY_NEXTCLOUD_E2E_ADMIN_PASSWORD ?? "test-only-non-production-password",
  });
  console.log(JSON.stringify({ status: "ok", login_redirect: "/login", login_page: "ok", ...result }));
} catch (error) {
  console.error(`Nextcloud verification failed: ${error.message}`);
  process.exitCode = 1;
}
