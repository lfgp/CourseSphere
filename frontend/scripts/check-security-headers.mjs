import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { createServer, preview } from 'vite';

const results = [];
const timeout = setTimeout(() => {
  console.error('Security-header HTTP checks exceeded 45 seconds.');
  process.exit(1);
}, 45_000);

function checkCommonHeaders(response) {
  assert.equal(response.headers.get('x-frame-options'), 'DENY');
  assert.equal(response.headers.get('x-content-type-options'), 'nosniff');
  assert.equal(response.headers.get('referrer-policy'), 'no-referrer');
  assert.equal(response.headers.get('permissions-policy'), 'camera=(), microphone=(), geolocation=()');
  const csp = response.headers.get('content-security-policy');
  assert.ok(csp.includes("frame-ancestors 'none'"));
  assert.ok(csp.includes("object-src 'none'"));
  assert.ok(csp.includes("form-action 'self'"));
  return csp;
}

const dev = await createServer({ server: { host: '127.0.0.1', port: 0 }, logLevel: 'silent' });
try {
  await dev.listen();
  console.log('Checking development HTML headers...');
  const address = dev.httpServer.address();
  const response = await fetch(`http://127.0.0.1:${address.port}/`, { signal: AbortSignal.timeout(10_000) });
  assert.equal(response.status, 200);
  const csp = checkCommonHeaders(response);
  assert.ok(csp.includes("script-src 'self' 'unsafe-inline'"));
  assert.ok(csp.includes('http://127.0.0.1:9099'));
  assert.ok(csp.includes('ws://127.0.0.1:9000'));
  await response.arrayBuffer();
  results.push({ target: 'vite-development', status: response.status, common_headers: true, emulator_connections_permitted_by_policy: true });
} finally {
  await dev.close();
}

const built = await preview({ preview: { host: '127.0.0.1', port: 0 }, logLevel: 'silent' });
try {
  console.log('Checking production HTML and entry script headers...');
  const address = built.httpServer.address();
  const response = await fetch(`http://127.0.0.1:${address.port}/`, { signal: AbortSignal.timeout(10_000) });
  assert.equal(response.status, 200);
  const csp = checkCommonHeaders(response);
  const scriptDirective = csp.split(';').map(value => value.trim()).find(value => value.startsWith('script-src '));
  assert.equal(scriptDirective, "script-src 'self'");
  assert.ok(!csp.includes('127.0.0.1'));
  assert.ok(!csp.includes("'unsafe-eval'"));
  assert.ok(csp.includes('https://identitytoolkit.googleapis.com'));
  const nginx = await readFile(new URL('../nginx.conf', import.meta.url), 'utf8');
  const nginxCsp = nginx.match(/add_header Content-Security-Policy "([^"]+)" always;/)?.[1];
  assert.equal(nginxCsp, csp, 'Nginx and preview must deliver the same production policy');
  const html = await response.text();
  const assetPath = html.match(/src="([^"]+\.js)"/)?.[1];
  assert.ok(assetPath, 'Built entry script must be present');
  const asset = await fetch(`http://127.0.0.1:${address.port}${assetPath}`, { signal: AbortSignal.timeout(10_000) });
  assert.equal(asset.status, 200);
  checkCommonHeaders(asset);
  await asset.arrayBuffer();
  results.push({ target: 'vite-production-preview', status: response.status, entry_asset_status: asset.status,
    common_headers: true, inline_scripts_disallowed_by_policy: true, nginx_policy_matches: true });
} finally {
  await new Promise((resolve, reject) => built.httpServer.close(error => error ? reject(error) : resolve()));
}

await writeFile(new URL('../../docs/evidence/security-headers-frontend.json', import.meta.url), JSON.stringify({
  checks_passed: true, results,
  limitation: 'HTTP responses and CSP configuration verified; no browser attack or Nginx container was executed.',
}, null, 2) + '\n');
console.log('Security headers verified on development HTML, built HTML and JavaScript; production CSP matches Nginx.');
clearTimeout(timeout);
