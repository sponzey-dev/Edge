import { assertLocalRedirect, assertLoginPage } from "./response-validation.mjs";

export async function checkLoginSurface(origin) {
  const root = await fetch(`${origin}/`, { redirect: "manual", signal: AbortSignal.timeout(10_000) });
  assertLocalRedirect(root.status, root.headers.get("location"), origin, "/login");
  const login = await fetch(`${origin}/login`, { redirect: "manual", signal: AbortSignal.timeout(10_000) });
  const html = await login.text();
  assertLoginPage(login.status, html);
  if (html.includes("/dist/core-login.js")) {
    const asset = await fetch(`${origin}/dist/core-login.js`, { redirect: "manual", signal: AbortSignal.timeout(10_000) });
    if (asset.status !== 200 || !(asset.headers.get("content-type") ?? "").includes("javascript")) {
      throw new Error("login script failed to load");
    }
    if ((await asset.arrayBuffer()).byteLength === 0) throw new Error("login script is empty");
  }
}
