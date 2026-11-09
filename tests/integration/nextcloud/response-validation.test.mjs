import assert from "node:assert/strict";
import test from "node:test";

import { assertLocalRedirect, assertLoginPage } from "./response-validation.mjs";

const origin = "http://127.0.0.1:18080";

test("accepts a local login redirect and rejects DNS-dependent or unexpected redirects", () => {
  assert.doesNotThrow(() => assertLocalRedirect(302, "/login", origin, "/login"));
  assert.doesNotThrow(() => assertLocalRedirect(302, `${origin}/login`, origin, "/login"));
  assert.throws(() => assertLocalRedirect(302, "http://nextcloud.test/login", origin, "/login"));
  assert.throws(() => assertLocalRedirect(502, "/login", origin, "/login"));
  assert.throws(() => assertLocalRedirect(302, "/other", origin, "/login"));
});

test("requires a successful login form or the Nextcloud login app shell", () => {
  const html = '<form id="login"><input name="user"><input name="password"><input name="requesttoken"></form>';
  assert.doesNotThrow(() => assertLoginPage(200, html));
  const shell = '<div id="login"></div><script src="/dist/core-login.js?v=1"></script>';
  assert.doesNotThrow(() => assertLoginPage(200, shell));
  assert.throws(() => assertLoginPage(200, '<div id="login"></div>'));
  assert.throws(() => assertLoginPage(502, html));
  assert.throws(() => assertLoginPage(200, "<html>service unavailable</html>"));
  assert.throws(() => assertLoginPage(200, '<form><input name="user"></form>'));
});
