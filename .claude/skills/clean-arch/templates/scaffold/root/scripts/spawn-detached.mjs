#!/usr/bin/env node
import fs from 'node:fs';
import { spawn } from 'node:child_process';

const [, , logFile, pidFile, command, ...args] = process.argv;

if (!logFile || !pidFile || !command) {
  console.error('usage: spawn-detached.mjs <log-file> <pid-file> <command> [args...]');
  process.exit(64);
}

const logFd = fs.openSync(logFile, 'w');
const child = spawn(command, args, {
  cwd: process.cwd(),
  detached: true,
  env: process.env,
  stdio: ['ignore', logFd, logFd],
});

child.once('error', (error) => {
  fs.closeSync(logFd);
  console.error(`failed to start ${command}: ${error.message}`);
  process.exit(1);
});

setImmediate(() => {
  if (!child.pid) {
    fs.closeSync(logFd);
    console.error(`failed to start ${command}: child pid was not assigned`);
    process.exit(1);
  }
  fs.writeFileSync(pidFile, `${child.pid}\n`);
  child.unref();
  fs.closeSync(logFd);
});
