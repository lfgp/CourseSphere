const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

function loadClient({ user = { getIdToken: async () => 'verified-test-token' }, ok = true } = {}) {
  const source = fs.readFileSync(path.join(__dirname, '../src/api.ts'), 'utf8');
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const calls = [];
  const auth = { currentUser: user };
  const signup = async (...args) => { calls.push({ signup: args }); return { user }; };
  const requireStub = (name) => {
    if (name === './firebase') return { auth };
    if (name === 'firebase/auth') return { createUserWithEmailAndPassword: signup };
    if (name === 'react-toastify') return { toast: {} };
    throw new Error(`Unexpected import ${name}`);
  };
  const fetchStub = async (url, options) => {
    calls.push({ url, options });
    return { ok, json: async () => ok ? { botResponse: 'demo' } : { error: 'Authentication required' } };
  };
  const exports = {};
  vm.compileFunction(compiled, ['require', 'exports', 'fetch'])(requireStub, exports, fetchStub);
  return { client: exports, calls, auth };
}

test('query waits for the ID token and sends it only in Authorization', async () => {
  const { client, calls } = loadClient();
  await client.fetchCourseSphereResponse('CS 1110');
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, '/api/users/query');
  assert.equal(calls[0].options.headers.Authorization, 'Bearer verified-test-token');
  assert.deepEqual(JSON.parse(calls[0].options.body), { query: 'CS 1110' });
  assert.equal(calls[0].options.cache, 'no-store');
  assert.equal(calls[0].options.credentials, 'omit');
});

test('signed-out requests fail before fetch', async () => {
  const { client, calls } = loadClient({ user: null });
  await assert.rejects(client.apiRequest('/users/info'), /log in/);
  assert.equal(calls.length, 0);
});

test('absolute and protocol-relative paths cannot receive the token', async () => {
  const { client, calls } = loadClient();
  for (const url of ['https://untrusted.example', '//untrusted.example']) {
    await assert.rejects(client.apiRequest(url), /Invalid API path/);
  }
  assert.equal(calls.length, 0);
});

test('HTTP failure is rejected instead of being presented as successful data', async () => {
  const { client } = loadClient({ ok: false });
  await assert.rejects(client.apiRequest('/users/info'), /Authentication required/);
});

test('registration calls the Firebase client SDK without an Admin API request', async () => {
  const { client, calls, auth } = loadClient();
  await client.createUser('user@example.test', 'test-password');
  assert.deepEqual(calls, [{ signup: [auth, 'user@example.test', 'test-password'] }]);
});
