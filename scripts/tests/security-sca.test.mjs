import assert from 'node:assert/strict';
import test from 'node:test';
import { classifyAuditRun, overallExitCode } from '../security-sca.mjs';

function output(vulnerable = false) {
  return JSON.stringify({ auditReportVersion: 2,
    vulnerabilities: vulnerable ? { example: { severity: 'high' } } : {},
    metadata: { vulnerabilities: { info: 0, low: 0, moderate: 0, high: vulnerable ? 1 : 0, critical: 0, total: vulnerable ? 1 : 0 } } });
}

test('a completed clean audit passes', () => {
  const result = classifyAuditRun({ status: 0, stdout: output() });
  assert.equal(result.status, 'clean');
  assert.equal(overallExitCode([result]), 0);
});

test('vulnerabilities fail the check, even if the external tool returns zero', () => {
  for (const status of [0, 1]) {
    const result = classifyAuditRun({ status, stdout: output(true) });
    assert.equal(result.status, 'vulnerable');
    assert.equal(overallExitCode([result]), 1);
  }
});

test('network failure, malformed output, missing counts or termination cannot pass as clean', () => {
  const cases = [
    { status: 1, stdout: JSON.stringify({ error: { code: 'ENETUNREACH' } }) },
    { status: 0, stdout: 'not JSON' },
    { status: 0, stdout: '{}' },
    { status: 0, stdout: output(), signal: 'SIGTERM' },
    { status: null, stdout: output(), error: new Error('timeout') },
    { status: 1, stdout: output() },
  ];
  for (const run of cases) {
    const result = classifyAuditRun(run);
    assert.equal(result.status, 'error');
    assert.equal(result.vulnerabilities, null);
    assert.equal(overallExitCode([result]), 2);
  }
});

test('inconsistent severity totals are rejected and errors take precedence over findings', () => {
  const report = JSON.parse(output(true));
  report.metadata.vulnerabilities.total = 0;
  const result = classifyAuditRun({ status: 0, stdout: JSON.stringify(report) });
  assert.equal(result.status, 'error');
  assert.equal(overallExitCode([{ status: 'vulnerable' }, result]), 2);
  assert.equal(overallExitCode([]), 2);
  assert.equal(overallExitCode([{ status: 'unknown' }]), 2);
});
