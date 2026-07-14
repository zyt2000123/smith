#!/usr/bin/env node
// Capture the directory from which the global CLI was invoked before any
// runtime/bootstrap code can change the process working directory.
process.env.SMITH_PROJECT_CWD ??= process.cwd();
await import("../dist/index.js");
