import assert from "node:assert/strict";
import http from "node:http";
import test from "node:test";

import { runUserFlow } from "./user-flow.mjs";

async function withFixture(callback, { acceptOversize = false, failLogin = false } = {}) {
  const files = new Map();
  const server = http.createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = Buffer.concat(chunks);
    if (req.url === "/login" && req.method === "GET") {
      res.writeHead(200, { "set-cookie": "fixture=initial; Path=/" });
      res.end('<html data-requesttoken="fixture-token"></html>');
    } else if (req.url === "/login" && req.method === "POST") {
      const params = new URLSearchParams(body.toString());
      const valid = !failLogin && params.get("user") === "fixture-user"
        && params.get("password") === "fixture-password" && params.get("requesttoken") === "fixture-token";
      res.writeHead(303, { location: valid ? "/apps/dashboard/" : "/login", "set-cookie": `session=${valid ? "valid" : "invalid"}; Path=/` });
      res.end();
    } else if (req.url === "/apps/files/" && req.method === "GET") {
      if (!(req.headers.cookie ?? "").includes("session=valid")) {
        res.writeHead(303, { location: "/login" }).end();
      } else {
        res.writeHead(200).end('<body id="body-user"></body>');
      }
    } else if (req.url.startsWith("/remote.php/dav/files/")) {
      if (req.headers.authorization !== `Basic ${Buffer.from("fixture-user:fixture-password").toString("base64")}`) {
        res.writeHead(401).end();
      } else if (req.method === "PROPFIND") {
        res.writeHead(207).end([...files.keys()].join("\n"));
      } else if (req.method === "PUT") {
        if (body.length > 1024 * 1024 && !acceptOversize) {
          res.writeHead(413).end();
        } else if (req.headers["if-none-match"] === "*" && files.has(req.url)) {
          res.writeHead(412).end();
        } else {
          files.set(req.url, body);
          res.writeHead(201).end();
        }
      } else if (req.method === "GET") {
        if (files.has(req.url)) res.writeHead(200).end(files.get(req.url));
        else res.writeHead(404).end();
      } else res.writeHead(405).end();
    } else res.writeHead(404).end();
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    await callback({ origin: `http://127.0.0.1:${server.address().port}`, username: "fixture-user", password: "fixture-password" });
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
}

test("user flow proves login, repeatable small-file use, and body-limit refusal", async () => {
  await withFixture(async (options) => {
    await runUserFlow(options);
    await runUserFlow(options);
  });
});

test("user flow rejects an accepted oversized upload", async () => {
  await withFixture(async (options) => {
    await assert.rejects(runUserFlow(options));
  }, { acceptOversize: true });
});

test("user flow rejects login that returns to the login page", async () => {
  await withFixture(async (options) => {
    await assert.rejects(runUserFlow(options));
  }, { failLogin: true });
});
