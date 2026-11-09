export function assertLocalRedirect(status, location, origin, pathname) {
  if (status !== 302 || !location) throw new Error("unexpected redirect status or missing location");
  const destination = new URL(location, origin);
  if (destination.origin !== origin) throw new Error("redirect left the local origin");
  if (destination.pathname !== pathname) throw new Error("unexpected redirect path");
}

export function assertLoginPage(status, html) {
  if (status !== 200) throw new Error("login page did not load");
  if (/<div\b[^>]*\bid=["']login["']/i.test(html)
      && /<script\b[^>]*\bsrc=["']\/dist\/core-login\.js(?:\?[^"']*)?["']/i.test(html)) {
    return;
  }
  if (!/<form\b/i.test(html)) throw new Error("login form missing");
  for (const name of ["user", "password", "requesttoken"]) {
    if (!new RegExp(`\\bname=["']${name}["']`, "i").test(html)) {
      throw new Error("login form field missing");
    }
  }
}
