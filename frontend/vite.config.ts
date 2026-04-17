import { defineConfig, type ProxyOptions } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";
import type { IncomingMessage } from "http";

const apiTarget = process.env.VITE_API_TARGET ?? "http://localhost:8000";

/** Paths the SPA calls when VITE_API_BASE is unset (local dev: same-origin /health, /bacnet, …). */
const bareApiRoutePrefixes = [
  "/ai",
  "/sites",
  "/equipment",
  "/points",
  "/timeseries",
  "/faults",
  "/run-fdd",
  "/download",
  "/capabilities",
  "/config",
  "/data-model",
  "/entities",
  "/jobs",
  "/bacnet",
  "/analytics",
  "/energy-calculations",
  "/health",
  "/docs",
  "/redoc",
  "/openapi.json",
  "/rules",
  "/auth",
];

/** React routes whose path starts with `/data-model` but are not API paths under `/data-model/*`. */
const DATA_MODEL_SPA_ROUTE_PREFIXES = ["/data-model-engineering", "/data-model-testing"] as const;

/** Serve the SPA for browser navigation; proxy only fetch/XHR to the API. */
function spaBypass(req: IncomingMessage) {
  const path = (req.url ?? "").split("?")[0] ?? "";
  if (
    DATA_MODEL_SPA_ROUTE_PREFIXES.some(
      (p) => path === p || path.startsWith(`${p}/`),
    )
  ) {
    return "/index.html";
  }
  if (req.headers.accept?.includes("text/html")) {
    return "/index.html";
  }
}

/** Docker / lab: VITE_API_BASE=/api → fetch /api/bacnet/… ; backend serves /bacnet/… (strip /api). */
function stripApiPrefix(path: string): string {
  const stripped = path.replace(/^\/api(?=\/|$)/, "");
  return stripped.length ? stripped : "/";
}

const bareApiProxy: ProxyOptions = {
  target: apiTarget,
  changeOrigin: true,
  bypass: spaBypass,
};

const bareRoutesFromPrefixes = Object.fromEntries(
  bareApiRoutePrefixes.map((r) => [r, { ...bareApiProxy }]),
) as Record<string, ProxyOptions>;

const devAndPreviewProxy: Record<string, ProxyOptions> = {
  // Must come before bare routes: matches /api/health, /api/bacnet/server_hello, …
  "/api": {
    target: apiTarget,
    changeOrigin: true,
    rewrite: (p: string) => stripApiPrefix(p),
  },
  ...bareRoutesFromPrefixes,
  "/ws": { target: apiTarget, changeOrigin: true, ws: true },
};

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: {
    host: "0.0.0.0",
    allowedHosts: ["localhost", ".local"],
    proxy: { ...devAndPreviewProxy },
  },
  preview: {
    // `vite preview` (Docker frontend) needs the same /api strip as dev; server.proxy is not always applied.
    host: "0.0.0.0",
    proxy: { ...devAndPreviewProxy },
  },
});
