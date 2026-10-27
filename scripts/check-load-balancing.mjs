import assert from 'node:assert/strict';
import { randomBytes, randomUUID } from 'node:crypto';
import { writeFile } from 'node:fs/promises';

const functional = process.argv.includes('--functional');
const base = 'http://127.0.0.1:8080';
const report = { scope: 'HTTP through the local Docker Compose Nginx gateway', health_requests: [], checks: {} };
const expected = new Set(['backend-1', 'backend-2']);

async function fetchLocal(url, options = {}) {
  return fetch(url, { ...options, signal: AbortSignal.timeout(15_000) });
}

function identify(response) {
  const instance = response.headers.get('x-backend-instance');
  const requestId = response.headers.get('x-request-id');
  assert.ok(expected.has(instance), 'The response must identify one of the two API instances');
  assert.match(requestId ?? '', /^[a-f0-9]{32}$/);
  return { instance, request_id: requestId, status: response.status };
}

async function api(path, options = {}) {
  const response = await fetchLocal(base + '/api' + path, options);
  const identity = identify(response);
  const data = await response.json();
  return { response, identity, data };
}

const page = await fetchLocal(base + '/');
assert.equal(page.status, 200, 'Frontend must be served by the gateway');
assert.equal(page.headers.get('x-frame-options'), 'DENY');
const policy = page.headers.get('content-security-policy');
assert.ok(policy?.includes("script-src 'self';"));
assert.ok(policy.includes('http://127.0.0.1:9099'));
const html = await page.text();
const asset = html.match(/src="([^"]+\.js)"/)?.[1];
assert.ok(asset, 'Built frontend must contain an entry script');
const javascript = await fetchLocal(base + asset);
assert.equal(javascript.status, 200);
await javascript.arrayBuffer();
report.checks.frontend_and_entry_asset = true;

for (let index = 1; index <= 8; index++) {
  const { response, identity, data } = await api('/health');
  assert.equal(response.status, 200);
  assert.deepEqual(data, { check: 'liveness', status: 'ok' });
  report.health_requests.push({ request: index, ...identity });
  console.log(`request=${index} status=${response.status} instance=${identity.instance} request_id=${identity.request_id}`);
}
const seen = new Set(report.health_requests.map(request => request.instance));
assert.equal(seen.size, 2, 'Both API instances must handle real HTTP requests');
assert.equal(new Set(report.health_requests.map(request => request.request_id)).size, 8);
report.checks.both_instances_served_requests = true;

for (const path of ['/api/metrics', '/api//metrics', '/api/%6Detrics']) {
  const response = await fetchLocal(base + path);
  assert.equal(response.status, 404, 'Public gateway must block metrics');
  await response.arrayBuffer();
}
report.checks.metrics_blocked_at_public_gateway = true;
const unauthorized = await api('/users/info');
assert.equal(unauthorized.response.status, 401);
report.checks.authentication_still_required = true;

if (functional) {
  const authBase = 'http://127.0.0.1:9099/identitytoolkit.googleapis.com/v1/accounts:';
  const databaseBase = 'http://127.0.0.1:9000';
  const created = await fetchLocal(authBase + 'signUp?key=demo-coursesphere-key', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: `container-${randomUUID()}@example.test`, password: randomBytes(24).toString('base64url'), returnSecureToken: true }),
  });
  assert.equal(created.status, 200, 'Firebase Auth emulator signup must succeed');
  const account = await created.json();
  const headers = { Authorization: `Bearer ${account.idToken}`, 'Content-Type': 'application/json' };
  try {
    const saved = await api('/users/info', { method: 'POST', headers, body: JSON.stringify({ about: 'Container smoke test' }) });
    assert.equal(saved.response.status, 200);
    const readers = new Set();
    for (let index = 0; index < 6; index++) {
      const profile = await api('/users/info', { headers });
      assert.equal(profile.response.status, 200);
      assert.equal(profile.data.about, 'Container smoke test');
      readers.add(profile.identity.instance);
    }
    assert.equal(readers.size, 2, 'Both instances must read the same Firebase profile');
    report.checks.shared_firebase_profile = true;

    const queries = [];
    for (let index = 0; index < 22; index++) {
      const result = await api('/users/query', { method: 'POST', headers, body: JSON.stringify({ query: 'CS 1110' }) });
      assert.equal(result.response.status, index < 20 ? 200 : 429, 'The two replicas must share the 20/minute UID quota');
      queries.push(result.identity);
    }
    assert.equal(new Set(queries.map(query => query.instance)).size, 2);
    report.query_quota = { accepted: 20, rejected: 2, requests: queries };
    report.checks.redis_quota_shared_between_instances = true;
    console.log('shared_profile=ok shared_redis_quota=20 accepted, 2 rejected across both instances');
  } finally {
    // auth= is the Firebase emulator REST protocol, never the application API.
    const removedData = await fetchLocal(`${databaseBase}/users/${encodeURIComponent(account.localId)}.json?ns=demo-coursesphere-default-rtdb&auth=${encodeURIComponent(account.idToken)}`, { method: 'DELETE' });
    assert.equal(removedData.status, 200, 'Remove only the temporary test user data');
    await removedData.arrayBuffer();
    const removedAccount = await fetchLocal(authBase + 'delete?key=demo-coursesphere-key', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ idToken: account.idToken }),
    });
    assert.equal(removedAccount.status, 200, 'Remove only the temporary emulator account');
    await removedAccount.arrayBuffer();
  }
}

report.successful = true;
report.limits = 'Local emulators and demo query implementation; not production Firebase, TLS, failover testing or a throughput benchmark.';
await writeFile(new URL('../docs/evidence/docker-load-balancing.json', import.meta.url), JSON.stringify(report, null, 2) + '\n');
console.log('Load balancing verified; sanitized evidence saved in docs/evidence/docker-load-balancing.json');
