import { readdir } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const shellDir = path.resolve(scriptDir, "..");
const sourceTests = (await readdir(path.join(shellDir, "src")))
  .filter((file) => /\.test\.[cm]?[jt]sx?$/.test(file))
  .sort();
const compiledTests = sourceTests.map((file) => path.join(shellDir, "dist", file.replace(/\.[cm]?[jt]sx?$/, ".js")));

// react-ink-markdown creates an internal MessagePort that outlives static
// renders in Node's test environment. Force exit only after Node has reported
// every test result, so this third-party handle cannot stall CI.
const result = spawnSync(process.execPath, ["--test", "--test-force-exit", ...compiledTests], {
  cwd: shellDir,
  stdio: "inherit",
});

process.exit(result.status ?? 1);
