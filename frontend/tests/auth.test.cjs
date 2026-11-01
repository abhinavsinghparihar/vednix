const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const ts = require("typescript");

// Execute the actual TypeScript modules, with only network/config dependencies
// replaced. Each test gets a fresh vault/store, just like reopening a browser.
function load(path, imports, globals = {}) {
  const source = ts.transpileModule(fs.readFileSync(`${__dirname}/../${path}`, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const exports = {};
  vm.runInNewContext(source, {
    exports, require: (name) => imports[name] ?? require(name),
    setTimeout, clearTimeout, AbortSignal, ...globals,
  });
  return exports;
}
const response = (body, status = 200) => new Response(JSON.stringify(body), { status });
const config = { API_BASE: "", API_BASE_CONFIGURED: true };
const user = { id: "owner", username: "owner" };

function vault(fetch, globals = {}) {
  return load("lib/tokenVault.ts", { "./config": config }, { fetch, ...globals });
}

test("new visitors skip refresh and its retry delay", async () => {
  const calls = [];
  const v = vault(async (url) => { calls.push(url); return response({ has_session: false, csrf_token: "csrf" }); });
  assert.equal((await v.tryRefresh()).ok, false);
  assert.deepEqual(calls, ["/api/auth/csrf"]);
});

test("reopened browser restores from cookie; parallel callers share one rotation", async () => {
  const calls = [];
  let locks = 0;
  const v = vault(async (url, init) => {
    calls.push(url);
    assert.equal(init.credentials, "include");
    if (url.endsWith("csrf")) return response({ has_session: true, csrf_token: "shared-nonce" });
    assert.equal(init.headers["X-CSRF-Token"], "shared-nonce");
    return response({ access_token: "new-access", user });
  }, { navigator: { locks: { request: async (_name, run) => { locks++; return run(); } } } });
  v.setCsrfToken("stale-tab-nonce");
  assert.equal(v.getAccessToken(), null);
  const results = await Promise.all([v.tryRefresh(), v.tryRefresh(), v.tryRefresh()]);
  assert.ok(results.every(r => r.ok));
  assert.equal(v.getAccessToken(), "new-access");
  assert.equal(locks, 1);
  assert.equal(calls.length, 2);
});

test("network failure is transient, not logout", async () => {
  const v = vault(async () => { throw new Error("offline"); });
  v.setAccessToken("existing");
  assert.equal((await v.tryRefresh()).transient, true);
  assert.equal(v.getAccessToken(), "existing");
});

test("stale CSRF is re-read before retrying", async () => {
  let reads = 0;
  const v = vault(async (url, init) => {
    if (url.endsWith("csrf")) return response({ has_session: true, csrf_token: `nonce-${++reads}` });
    if (reads === 1) return response({}, 403);
    assert.equal(init.headers["X-CSRF-Token"], "nonce-2");
    return response({ access_token: "restored", user });
  });
  assert.equal((await v.tryRefresh()).ok, true);
  assert.equal(reads, 2);
});

function store(result, status = async () => { throw new Error("providers offline"); }) {
  let refreshes = 0;
  const { useAuth } = load("store/auth.ts", {
    "@/lib/authApi": { authApi: {}, onboardingApi: { status } },
    "@/lib/tokenVault": {
      ApiError: class extends Error {}, getAccessToken: () => null,
      tryRefresh: async () => { refreshes++; return result; },
    },
  });
  return { useAuth, refreshes: () => refreshes };
}

test("guest entry never waits for onboarding/provider services", async () => {
  let called = false;
  const { useAuth } = store({ ok: false }, async () => { called = true; return new Promise(() => {}); });
  await useAuth.getState().bootstrap();
  assert.equal(useAuth.getState().session, "locked");
  assert.equal(called, false);
});

test("cold-start network failure stays unknown, not locked", async () => {
  const { useAuth } = store({ ok: false, transient: true });
  await useAuth.getState().bootstrap();
  assert.equal(useAuth.getState().session, "unknown");
});

test("valid login survives onboarding outage; duplicate bootstraps are deduplicated", async () => {
  const { useAuth, refreshes } = store({ ok: true, user });
  await Promise.all([useAuth.getState().bootstrap(), useAuth.getState().bootstrap()]);
  assert.equal(useAuth.getState().session, "authed");
  assert.equal(useAuth.getState().user, user);
  assert.equal(refreshes(), 1);
});

test("confirmed expired/revoked session clears the access token", async () => {
  const v = vault(async (url) => url.endsWith("csrf")
    ? response({ has_session: true, csrf_token: "csrf" })
    : response({ detail: "revoked" }, 401));
  v.setAccessToken("expired");
  const result = await v.tryRefresh();
  assert.equal(result.ok, false);
  assert.equal(Boolean(result.transient), false);
  assert.equal(v.getAccessToken(), null);
});

test("backend restart/5xx does not clear the device session", async () => {
  const v = vault(async (url) => url.endsWith("csrf")
    ? response({ has_session: true, csrf_token: "csrf" })
    : response({}, 503));
  v.setAccessToken("existing");
  assert.equal((await v.tryRefresh()).transient, true);
  assert.equal(v.getAccessToken(), "existing");
});
