import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const severities = ['info', 'low', 'moderate', 'high', 'critical'];
const auditArguments = ['audit', '--json', '--package-lock-only', '--ignore-scripts',
  '--audit-level=low', '--include=prod', '--include=dev', '--include=optional', '--include=peer',
  '--fetch-retries=1', '--fetch-timeout=30000'];

export function classifyAuditRun(run) {
  const error = { status: 'error', exit_code: Number.isInteger(run.status) ? run.status : null,
    vulnerabilities: null, report: { execution_error: 'npm audit did not complete with a valid report.' } };
  if (run.error || run.signal || ![0, 1].includes(run.status)) return error;
  let report;
  try { report = JSON.parse(run.stdout); } catch { return error; }
  const counts = report?.metadata?.vulnerabilities;
  if (report.error || report.auditReportVersion !== 2 || !counts || !report.vulnerabilities
      || typeof report.vulnerabilities !== 'object' || Array.isArray(report.vulnerabilities)
      || ![...severities, 'total'].every(key => Number.isSafeInteger(counts[key]) && counts[key] >= 0)
      || severities.reduce((sum, key) => sum + counts[key], 0) !== counts.total
      || Object.keys(report.vulnerabilities).length !== counts.total) return error;
  if (counts.total === 0 && run.status !== 0) return error;
  return { status: counts.total > 0 ? 'vulnerable' : 'clean', exit_code: run.status,
    vulnerabilities: counts, report };
}

export function overallExitCode(results) {
  if (!results.length || results.some(result => !['clean', 'vulnerable'].includes(result.status))) return 2;
  return results.some(result => result.status === 'vulnerable') ? 1 : 0;
}

function writeJSON(path, value) {
  writeFileSync(path, JSON.stringify(value, null, 2) + '\n', 'utf8');
}

function main() {
  const output = resolve(root, process.env.SCA_OUTPUT_DIR || 'docs/evidence');
  mkdirSync(output, { recursive: true });
  const npmCLI = process.env.npm_execpath;
  // npm run supplies the CLI path. Invoke Node directly: no shell or platform-specific quoting.
  const npmAvailable = Boolean(npmCLI && existsSync(npmCLI));
  const execute = (args, cwd) => spawnSync(process.execPath, [npmCLI, ...args], {
    cwd, encoding: 'utf8', windowsHide: true, timeout: 90_000, maxBuffer: 16 * 1024 * 1024,
    env: { ...process.env, NO_COLOR: '1', npm_config_color: 'false' },
  });
  const version = npmAvailable ? execute(['--version'], root) : {};
  const summary = {
    schema_version: 1, tool: 'npm audit', analysis_type: 'SCA',
    started_at: new Date().toISOString(), node_version: process.version,
    npm_version: version.status === 0 ? version.stdout.trim() : null,
    command: 'npm ' + auditArguments.join(' '), audit_level: 'low',
    scope: 'All dependency types in the root and frontend npm lockfiles; no Python or OS package scan.',
    results: [],
  };

  for (const [name, directory] of [['root', root], ['frontend', join(root, 'frontend')]]) {
    console.log(`SCA: auditing ${name} lockfile...`);
    const lockfile = join(directory, 'package-lock.json');
    const reportName = `sca-npm-${name}.json`;
    const available = npmAvailable && version.status === 0 && existsSync(lockfile);
    const raw = available ? execute(auditArguments, directory) : {};
    const classified = classifyAuditRun(raw);
    writeJSON(join(output, reportName), classified.report);
    summary.results.push({ name, lockfile: name === 'root' ? 'package-lock.json' : 'frontend/package-lock.json',
      lockfile_sha256: existsSync(lockfile) ? createHash('sha256').update(readFileSync(lockfile)).digest('hex') : null,
      status: classified.status, exit_code: classified.exit_code,
      vulnerabilities: classified.vulnerabilities, report: reportName });
    console.log(`SCA: ${name}: ${classified.status}`);
  }
  summary.finished_at = new Date().toISOString();
  summary.exit_code = overallExitCode(summary.results);
  summary.successful = summary.exit_code === 0;
  summary.limitations = 'Known advisories for the resolved inventory; not proof of exploitability or absence of unknown vulnerabilities. Network/tool failures are errors, not clean scans.';
  writeJSON(join(output, 'sca-summary.json'), summary);
  const lines = [
    `Tool: ${summary.tool} (SCA)`, `Started (UTC): ${summary.started_at}`,
    `Node: ${summary.node_version}; npm: ${summary.npm_version ?? 'unavailable'}`,
    `Command: ${summary.command}`,
    ...summary.results.map(result => `${result.name}: ${result.status}; npm exit=${result.exit_code ?? 'unavailable'}; vulnerabilities=${result.vulnerabilities?.total ?? 'not assessed'}`),
    `Overall exit code: ${summary.exit_code}`, `Scope: ${summary.scope}`, `Limits: ${summary.limitations}`,
  ];
  writeFileSync(join(output, 'sca-execution.txt'), lines.join('\n') + '\n', 'utf8');
  console.log(lines.join('\n'));
  if (!npmAvailable) console.error('Run this check with npm run security:sca.');
  process.exitCode = summary.exit_code;
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  try { main(); } catch {
    console.error('SCA could not finish or write its reports; results are not assessed.');
    process.exitCode = 2;
  }
}
