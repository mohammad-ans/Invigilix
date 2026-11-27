import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { defineConfig } from "vite";
import { deliveryPath } from "./routes.mjs";

const target = "http://127.0.0.1:8000";
const proxy = {
  "/api/": { target },
  [deliveryPath]: {
    target,
    bypass(req) { if (req.headers.accept !== "application/json") return "/index.html"; },
    rewrite: path => "/api" + path,
  },
};

export default defineConfig({
  server: { proxy },
  preview: { proxy },
  plugins: [{
    name: "offline-attempt-shell",
    generateBundle(_, bundle) {
      const assets = Object.keys(bundle).filter(path => /\.(js|css)$/.test(path)).map(path => "/" + path);
      const install = readFileSync("src/features/delivery/offline-shell.js", "utf8")
        .replace("export function installDeliveryShell", "function installDeliveryShell");
      const version = createHash("sha256").update(install + assets.join("|")).digest("hex").slice(0, 16);
      const config = { version, shell: "/index.html", assets };
      this.emitFile({ type: "asset", fileName: "sw.js", source: install + "\ninstallDeliveryShell(self," + JSON.stringify(config) + ");" });
    },
  }],
});
