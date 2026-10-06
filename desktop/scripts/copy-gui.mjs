// Copies the GUI into the Tauri bundle folder, leaving out test files and their dependencies.
// Cross-platform replacement for the rsync/rm/mkdir sequence, which needs POSIX tools.
import { cpSync, mkdirSync, rmSync } from "node:fs";
import { basename } from "node:path";

const [, , source, target] = process.argv;
if (!source || !target) {
  console.error("usage: node scripts/copy-gui.mjs <source-dir> <target-dir>");
  process.exit(2);
}

const excludedDir = new Set(["node_modules", "test-support"]);
const excludedFile = /\.test\.js$|^package(-lock)?\.json$/;

rmSync(target, { recursive: true, force: true });
mkdirSync(target, { recursive: true });
cpSync(source, target, {
  recursive: true,
  filter: (path) => {
    const name = basename(path);
    return !excludedDir.has(name) && !excludedFile.test(name);
  },
});
