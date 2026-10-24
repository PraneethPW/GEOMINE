import fs from "node:fs";
import path from "node:path";
import { gzipSync } from "node:zlib";
const root = path.resolve("dist");
const manifest = JSON.parse(
  fs.readFileSync(path.join(root, ".vite/manifest.json"), "utf8"),
);
const initial = new Set();
function visit(key) {
  if (initial.has(key)) return;
  initial.add(key);
  for (const next of manifest[key].imports || []) visit(next);
}
for (const [key, value] of Object.entries(manifest)) if (value.isEntry) visit(key);
let javascript = 0,
  css = 0;
const styles = new Set();
for (const key of initial) {
  const item = manifest[key];
  if (
    /Workspace|managedIdentity|ManagedAuth|MapView|Globe|\/three-|\/map-/.test(
      item.file,
    )
  )
    throw new Error(`Private/heavy code preloaded by public entry: ${item.file}`);
  javascript += gzipSync(fs.readFileSync(path.join(root, item.file))).length;
  for (const file of item.css || []) styles.add(file);
}
for (const file of styles)
  css += gzipSync(fs.readFileSync(path.join(root, file))).length;
if (javascript > 160 * 1024 || css > 35 * 1024)
  throw new Error(`Public entry exceeds gzip budget: JS ${javascript}, CSS ${css}`);
console.log(
  JSON.stringify({
    publicInitialJavascriptGzipBytes: javascript,
    publicCssGzipBytes: css,
    budget: "passed",
    privateWorkspaceAnd3dDeferred: true,
  }),
);
