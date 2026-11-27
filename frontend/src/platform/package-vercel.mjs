import { cp, mkdir, writeFile } from "node:fs/promises";
import { vercelRoutes } from "./routes.mjs";

if (process.env.VERCEL || process.env.API_ORIGIN) {
  if (!process.env.API_ORIGIN) throw Error("Set API_ORIGIN to your FastAPI HTTPS origin in Vercel.");
  const api = new URL(process.env.API_ORIGIN);
  if (api.protocol !== "https:" || api.href !== api.origin + "/") throw Error("API_ORIGIN must be a bare HTTPS origin.");
  const output = ".vercel/output";
  await mkdir(output, { recursive: true });
  await cp("dist", output + "/static", { recursive: true });
  await writeFile(output + "/config.json", JSON.stringify({ version: 3, routes: vercelRoutes(api.origin) }, null, 2));
}
