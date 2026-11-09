import { randomUUID } from "node:crypto";

const bodyLimit = 1024 * 1024;
const sentinelName = "sponzey-edge-e2e-sentinel-v1.txt";
const sentinelContents = Buffer.from("Sponzey Edge reusable Nextcloud fixture v1\n");

function requireStatus(response, allowed, step) {
  if (!allowed.includes(response.status)) throw new Error(`${step}: unexpected HTTP status ${response.status}`);
}

export async function runUserFlow({ origin, username, password }) {
  if (!username || !password) throw new Error("test credentials are required");
  const cookies = new Map();
  const cookieHeader = () => [...cookies].map(([key, value]) => `${key}=${value}`).join("; ");
  const request = async (path, options = {}) => {
    const response = await fetch(`${origin}${path}`, {
      ...options,
      redirect: "manual",
      signal: AbortSignal.timeout(15_000),
    });
    for (const header of response.headers.getSetCookie()) {
      const first = header.split(";", 1)[0];
      const separator = first.indexOf("=");
      if (separator > 0) cookies.set(first.slice(0, separator), first.slice(separator + 1));
    }
    return response;
  };

  const loginPage = await request("/login");
  requireStatus(loginPage, [200], "login page");
  const html = await loginPage.text();
  const token = html.match(/\bdata-requesttoken=["']([^"']+)["']/i)?.[1];
  if (!token) throw new Error("login request token missing");
  const login = await request("/login", {
    method: "POST",
    headers: { cookie: cookieHeader(), "content-type": "application/x-www-form-urlencoded", origin },
    body: new URLSearchParams({ user: username, password, requesttoken: token }),
  });
  requireStatus(login, [302, 303], "login POST");
  const location = login.headers.get("location");
  if (!location) throw new Error("login redirect missing");
  const destination = new URL(location, origin);
  if (destination.origin !== origin || destination.pathname.startsWith("/login")) {
    throw new Error("login did not reach an authenticated local page");
  }

  for (let attempt = 0; attempt < 2; attempt += 1) {
    const page = await request("/apps/files/", { headers: { cookie: cookieHeader() } });
    requireStatus(page, [200], "authenticated files page");
    if (!(await page.text()).includes('id="body-user"')) throw new Error("authenticated files page missing");
  }

  const root = `/remote.php/dav/files/${encodeURIComponent(username)}/`;
  const file = `${root}${sentinelName}`;
  const authorization = `Basic ${Buffer.from(`${username}:${password}`).toString("base64")}`;
  const headers = { authorization };
  const anonymous = await request(root, { method: "PROPFIND", headers: { depth: "1" } });
  requireStatus(anonymous, [401, 403], "anonymous WebDAV");

  const existing = await request(file, { headers });
  requireStatus(existing, [200, 404], "sentinel lookup");
  if (existing.status === 200) {
    if (!Buffer.from(await existing.arrayBuffer()).equals(sentinelContents)) {
      throw new Error("existing sentinel is not owned by this fixture");
    }
  } else {
    const upload = await request(file, {
      method: "PUT", headers: { ...headers, "if-none-match": "*" }, body: sentinelContents,
    });
    requireStatus(upload, [201, 204], "small upload");
  }
  const listing = await request(root, { method: "PROPFIND", headers: { ...headers, depth: "1" } });
  requireStatus(listing, [207], "file listing");
  if (!(await listing.text()).includes(sentinelName)) throw new Error("sentinel missing from file listing");
  const download = await request(file, { headers });
  requireStatus(download, [200], "small download");
  if (!Buffer.from(await download.arrayBuffer()).equals(sentinelContents)) throw new Error("download content mismatch");

  const oversizedFile = `${root}sponzey-edge-e2e-oversize-${randomUUID()}.bin`;
  const oversized = await request(oversizedFile, {
    method: "PUT", headers: { ...headers, "if-none-match": "*" }, body: Buffer.alloc(bodyLimit + 1),
  });
  requireStatus(oversized, [413], "oversized upload");
  const absent = await request(oversizedFile, { headers });
  requireStatus(absent, [404], "oversized file absence");
  return { login: "ok", session: "ok", smallFile: "ok", oversized: "rejected", sentinel: "preserved" };
}
