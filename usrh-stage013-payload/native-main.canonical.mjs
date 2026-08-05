#!/usr/bin/env node
import os from 'node:os';
import path from 'node:path';
import fs from 'node:fs';
import { pathToFileURL } from 'node:url';
import { createNativeSession } from './native-session.mjs';
import { readFrame, writeFrame } from './native-framing.mjs';

export const HOST_NAME = 'com.metablooms.universal_resource_harvester';

function defaultDbPath() {
  const base = process.env.LOCALAPPDATA || process.env.XDG_STATE_HOME || path.join(os.homedir(), '.local', 'state');
  return path.join(base, 'MetaBlooms', 'UniversalResourceHarvester', 'jobs.sqlite');
}

function hostError(code, detail) {
  return {protocolVersion: '1.0', jobId: 'host', sequence: 0, type: 'host.error', payload: {code, ...(detail ? {detail} : {})}};
}

export async function runNativeHost({input = process.stdin, output = process.stdout, dbPath = process.env.USRH_DB_PATH || defaultDbPath()} = {}) {
  fs.mkdirSync(path.dirname(dbPath), {recursive: true});
  const session = createNativeSession({dbPath});
  let exitCode = 0;
  const close = () => session.close();
  process.once('SIGTERM', close);
  process.once('SIGINT', close);
  try {
    await writeFrame(output, {
      protocolVersion: '1.0',
      jobId: 'host',
      sequence: 0,
      type: 'host.ready',
      payload: {hostName: HOST_NAME, capabilityToken: session.capabilityToken, maxMessageBytes: 1024 * 1024}
    });
    while (true) {
      let message;
      try {
        message = await readFrame(input);
      } catch (error) {
        const code = error?.message || 'E_FRAME_READ';
        try { await writeFrame(output, hostError(code)); } catch {}
        if (code === 'E_MALFORMED_JSON') continue;
        exitCode = 2;
        if (typeof input.destroy === 'function') input.destroy();
        break;
      }
      if (message === null) break;
      await writeFrame(output, await session.handle(message));
    }
  } finally {
    close();
    process.removeListener('SIGTERM', close);
    process.removeListener('SIGINT', close);
  }
  return exitCode;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const code = await runNativeHost();
  process.exitCode = code;
}
