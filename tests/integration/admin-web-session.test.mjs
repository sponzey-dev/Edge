import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../../apps/admin-web/app.js", import.meta.url), "utf8");

function page(requests = []) {
  const context = vm.createContext({
    document: { addEventListener() {} },
    window: { crypto: { randomUUID: () => "fixture-request" } },
    fetch: async (url, options) => {
      requests.push({ url, options });
      const payload = url.endsWith("/login") ? { csrf_token: "fixture-csrf" } : {};
      return { ok: true, status: 200, text: async () => JSON.stringify(payload) };
    },
    URLSearchParams,
    console,
  });
  vm.runInContext(source, context, { filename: "app.js" });
  vm.runInContext("render = () => {}; elements.loginPasswordHash = { value: 'fixture-hash' };", context);
  return context;
}

test("login uses the in-memory CSRF token and logout clears it", async () => {
  const requests = [];
  const context = page(requests);
  vm.runInContext("refreshProtected = async () => {};", context);
  await vm.runInContext("login({ preventDefault() {} })", context);
  await vm.runInContext("api.createSupportBundle()", context);
  assert.equal(requests.at(-1).options.headers["X-CSRF-Token"], "fixture-csrf");
  await vm.runInContext("logout()", context);
  assert.equal(requests.at(-1).url, "/api/v1/logout");
  assert.equal(vm.runInContext("state.csrfToken", context), "");
});

test("reload with only a session cookie requires login rather than showing an editable session", async () => {
  const context = page();
  vm.runInContext(`
    for (const name of ["config", "proxyHosts", "upstreamHealth", "metrics", "certificates", "trustBundles", "accessLogs", "errorLogs"]) {
      api[name] = async () => ({});
    }
    loadAudit = async () => {};
  `, context);
  await vm.runInContext("refreshProtected()", context);
  assert.equal(vm.runInContext("state.authenticated", context), false);
  assert.equal(vm.runInContext("state.csrfToken", context), "");
});

test("a rejected CSRF token clears in-memory state and allows login again", () => {
  const context = page();
  vm.runInContext(`
    state.authenticated = true;
    state.csrfToken = "stale-token";
    handleError(new ApiError("csrf token is required", { status: 403, code: "ADMIN_CSRF_REQUIRED" }));
  `, context);
  assert.equal(vm.runInContext("state.authenticated", context), false);
  assert.equal(vm.runInContext("state.csrfToken", context), "");
});
