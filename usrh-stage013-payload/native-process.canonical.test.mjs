import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { encodeFrame, readFrame } from '../src/native-framing.mjs';

const main = new URL('../src/native-main.mjs', import.meta.url);
const mainPath = fileURLToPath(main);

const startPayload = token => ({
  protocolVersion: '1.0', jobId: 'process-job', sequence: 1, type: 'job.start', capabilityToken: token,
  payload: {
    seedUrl: 'https://example.test/start',
    scope: {mode: 'smart', allowedHosts: ['example.test'], allowedPathPrefixes: ['/'], terminalResourceHosts: [], limits: {maxPages: 5, maxDepth: 2, maxBytes: 1000, maxRuntimeSeconds: 30, maxRequestsPerMinute: 10, maxExternalHops: 0}},
    authorization: {artifactSha256: 'b'.repeat(64), allowedActions: ['navigate'], forbiddenDataClasses: ['student-records']}
  }
});

test('native process emits ready token, accepts one frame, and closes cleanly on EOF', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'usrh-native-process-'));
  const child = spawn(process.execPath, [mainPath], {stdio: ['pipe','pipe','pipe'], env: {...process.env, USRH_DB_PATH: path.join(dir, 'jobs.sqlite')}});
  try {
    const ready = await readFrame(child.stdout);
    assert.equal(ready.type, 'host.ready');
    assert.match(ready.payload.capabilityToken, /^[A-Za-z0-9_-]{43}$/);
    child.stdin.write(encodeFrame(startPayload(ready.payload.capabilityToken)));
    const ack = await readFrame(child.stdout);
    assert.equal(ack.type, 'ack');
    child.stdin.end();
    const code = await new Promise(resolve => child.once('exit', resolve));
    assert.equal(code, 0);
  } finally {
    child.kill('SIGKILL'); fs.rmSync(dir, {recursive: true, force: true});
  }
});

test('malformed JSON receives structured rejection and does not terminate the host', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'usrh-native-process-'));
  const child = spawn(process.execPath, [mainPath], {stdio: ['pipe','pipe','pipe'], env: {...process.env, USRH_DB_PATH: path.join(dir, 'jobs.sqlite')}});
  try {
    const ready = await readFrame(child.stdout);
    const bad = Buffer.from('{bad', 'utf8');
    const header = Buffer.alloc(4); header.writeUInt32LE(bad.length);
    child.stdin.write(Buffer.concat([header, bad]));
    const error = await readFrame(child.stdout);
    assert.equal(error.type, 'host.error');
    assert.equal(error.payload.code, 'E_MALFORMED_JSON');
    child.stdin.write(encodeFrame(startPayload(ready.payload.capabilityToken)));
    assert.equal((await readFrame(child.stdout)).type, 'ack');
    child.stdin.end();
    assert.equal(await new Promise(resolve => child.once('exit', resolve)), 0);
  } finally {
    child.kill('SIGKILL'); fs.rmSync(dir, {recursive: true, force: true});
  }
});

test('oversized length fails closed after one structured host error', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'usrh-native-process-'));
  const child = spawn(process.execPath, [mainPath], {stdio: ['pipe','pipe','pipe'], env: {...process.env, USRH_DB_PATH: path.join(dir, 'jobs.sqlite')}});
  try {
    await readFrame(child.stdout);
    const header = Buffer.alloc(4); header.writeUInt32LE(1024 * 1024 + 1);
    child.stdin.write(header);
    const error = await readFrame(child.stdout);
    assert.equal(error.type, 'host.error');
    assert.equal(error.payload.code, 'E_MESSAGE_TOO_LARGE');
    assert.equal(await new Promise(resolve => child.once('exit', resolve)), 2);
  } finally {
    child.kill('SIGKILL'); fs.rmSync(dir, {recursive: true, force: true});
  }
});

test('each native-host process emits a distinct capability token', async () => {
  const dirs = [0,1].map(() => fs.mkdtempSync(path.join(os.tmpdir(), 'usrh-native-token-')));
  const children = dirs.map((dir, i) => spawn(process.execPath, [mainPath], {stdio: ['pipe','pipe','pipe'], env: {...process.env, USRH_DB_PATH: path.join(dir, `jobs-${i}.sqlite`)}}));
  try {
    const ready = await Promise.all(children.map(child => readFrame(child.stdout)));
    assert.notEqual(ready[0].payload.capabilityToken, ready[1].payload.capabilityToken);
    for (const child of children) child.stdin.end();
    assert.deepEqual(await Promise.all(children.map(child => new Promise(resolve => child.once('exit', resolve)))), [0,0]);
  } finally {
    for (const child of children) child.kill('SIGKILL');
    for (const dir of dirs) fs.rmSync(dir, {recursive:true, force:true});
  }
});

test('direct execution detection uses a platform-correct file URL', () => {
  const source = fs.readFileSync(main, 'utf8');
  assert.match(source, /import \{ pathToFileURL \} from 'node:url';/);
  assert.match(source, /pathToFileURL\(process\.argv\[1\]\)\.href/);
  assert.equal(mainPath, fileURLToPath(main));
  assert.doesNotMatch(source, /`file:\/\/\$\{process\.argv\[1\]\}`/);
});
