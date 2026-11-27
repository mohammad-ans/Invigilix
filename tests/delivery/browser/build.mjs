import { copyFile, readFile, readdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "vite";

export async function buildCandidateShell(out) {
  const root = fileURLToPath(new URL("./", import.meta.url));
  await build({ root, logLevel: "warn", build: { outDir: out, emptyOutDir: true } });
  const assets = (await readdir(join(out, "assets"))).map(file => "/assets/" + file);
  await copyFile(join(out, "index.html"), join(out, "shell.html"));
  const worker = new URL("../../../frontend/src/features/delivery/offline-shell.js", import.meta.url);
  const options = { version: "fixture", shell: "/shell.html", assets };
  await writeFile(join(out, "sw.js"),
    await readFile(worker, "utf8") + "\ninstallDeliveryShell(self," + JSON.stringify(options) + ");");
  return assets;
}
