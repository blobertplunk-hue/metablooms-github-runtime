import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import https from 'node:https';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

export const CFT_VERSION = '152.0.7977.82';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const platform = process.platform === 'linux' ? 'linux64' : process.platform === 'win32' ? 'win64' : process.arch === 'arm64' ? 'mac-arm64' : 'mac-x64';
const archiveName = `chrome-${platform}.zip`;
const url = `https://storage.googleapis.com/chrome-for-testing-public/${CFT_VERSION}/${platform}/${archiveName}`;
const cacheRoot = path.join(root, '.cache', 'chrome-for-testing', CFT_VERSION, platform);
const extractedRoot = path.join(cacheRoot, `chrome-${platform}`);
const binaryName = process.platform === 'win32' ? 'chrome.exe' : process.platform === 'darwin' ? 'Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing' : 'chrome';
const cachedBinary = path.join(extractedRoot, binaryName);

function versionOf(binary) {
  const text = execFileSync(binary, ['--version'], { encoding: 'utf8' }).trim();
  const match = text.match(/(\d+\.\d+\.\d+\.\d+)/);
  if (!match) throw new Error(`Chrome for Testing version unavailable: ${text}`);
  return { text, version: match[1] };
}

export function verifyCftBinary(binary) {
  const resolved = path.resolve(binary);
  if (!fs.existsSync(resolved)) throw new Error(`Chrome for Testing binary missing: ${resolved}`);
  const found = versionOf(resolved);
  if (found.version !== CFT_VERSION) {
    throw new Error(`Chrome for Testing version mismatch: required ${CFT_VERSION}, got ${found.version} (${found.text})`);
  }
  return resolved;
}

function download(source, destination) {
  return new Promise((resolve, reject) => {
    const request = https.get(source, { headers: { 'user-agent': 'MetaChat-v0.7.0-CFT-fetcher' } }, (response) => {
      if ([301,302,303,307,308].includes(response.statusCode ?? 0) && response.headers.location) {
        response.resume();
        download(response.headers.location, destination).then(resolve, reject);
        return;
      }
      if (response.statusCode !== 200) {
        response.resume();
        reject(new Error(`Chrome for Testing download failed HTTP ${response.statusCode}`));
        return;
      }
      const out = fs.createWriteStream(destination, { flags: 'wx' });
      response.pipe(out);
      out.on('finish', () => out.close(resolve));
      out.on('error', reject);
    });
    request.on('error', reject);
  });
}

export async function getCftPath() {
  if (process.env.METACHAT_CFT_BIN) return verifyCftBinary(process.env.METACHAT_CFT_BIN);
  if (fs.existsSync(cachedBinary)) return verifyCftBinary(cachedBinary);

  fs.mkdirSync(cacheRoot, { recursive: true });
  const archive = path.join(cacheRoot, archiveName);
  if (!fs.existsSync(archive)) {
    const partial = `${archive}.partial-${process.pid}`;
    await download(url, partial);
    fs.renameSync(partial, archive);
  }
  fs.rmSync(extractedRoot, { recursive: true, force: true });
  execFileSync('unzip', ['-q', archive, '-d', cacheRoot], { stdio: 'inherit' });
  if (process.platform !== 'win32') fs.chmodSync(cachedBinary, 0o755);
  return verifyCftBinary(cachedBinary);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  getCftPath().then((p) => process.stdout.write(`${p}\n`)).catch((error) => {
    process.stderr.write(`${error.stack ?? error}\n`);
    process.exitCode = 1;
  });
}
