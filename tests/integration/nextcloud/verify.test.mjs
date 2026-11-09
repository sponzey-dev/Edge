import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import http from "node:http";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { checkLoginSurface } from "./login-surface.mjs";

async function withServer(loginStatus, callback, assetStatus = 200) {
  const server = http.createServer((request, response) => {
    if (request.url === "/") {
      response.writeHead(302, { Location: `http://127.0.0.1:${server.address().port}/login` });
      response.end();
    } else if (request.url === "/login") {
      response.writeHead(loginStatus, { "content-type": "text/html" });
      response.end('<div id="login"></div><script src="/dist/core-login.js?v=1"></script>');
    } else if (request.url.startsWith("/dist/core-login.js")) {
      response.writeHead(assetStatus, { "content-type": "application/javascript" });
      response.end("/* fixture */");
    } else {
      response.writeHead(404).end();
    }
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    const port = server.address().port;
    return await callback(port);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
}

function runVerifier(port) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [fileURLToPath(new URL("./verify.mjs", import.meta.url))], {
      env: { ...process.env, SPONZEY_NEXTCLOUD_EDGE_PORT: String(port) },
      stdio: ["ignore", "pipe", "pipe"],
    });
    let output = "";
    child.stdout.on("data", (chunk) => { output += chunk; });
    child.stderr.on("data", (chunk) => { output += chunk; });
    child.on("error", reject);
    child.on("close", (status) => resolve({ status, output }));
  });
}

test("verifier checks a local login page after the redirect", async () => {
  await withServer(200, async (port) => {
    await assert.doesNotReject(checkLoginSurface(`http://127.0.0.1:${port}`));
  });
});

test("a redirect followed by a broken login page fails verification", async () => {
  await withServer(502, async (port) => {
    await assert.rejects(checkLoginSurface(`http://127.0.0.1:${port}`));
  });
});

test("a login shell with a broken script fails verification", async () => {
  await withServer(200, async (port) => {
    await assert.rejects(checkLoginSurface(`http://127.0.0.1:${port}`));
  }, 502);
});

test("the full verifier must not report success when only the login shell works", async () => {
  await withServer(200, async (port) => {
    const result = await runVerifier(port);
    assert.notEqual(result.status, 0);
  });
});
