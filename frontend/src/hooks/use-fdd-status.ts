import { useQuery } from "@tanstack/react-query";
import { apiFetch, resolveApiUrl } from "@/lib/api";
import { stackStatusConsoleDebug, stackStatusConsoleError } from "@/lib/stack-status-console";
import type { FddRunStatus, HealthStatus, Capabilities } from "@/types/api";

export function useFddStatus() {
  return useQuery<FddRunStatus>({
    queryKey: ["fdd-status"],
    queryFn: () => apiFetch<FddRunStatus>("/run-fdd/status"),
    refetchInterval: 60_000,
  });
}

export function useHealth() {
  return useQuery<HealthStatus>({
    queryKey: ["health"],
    queryFn: async () => {
      const path = "/health";
      const url = resolveApiUrl(path);
      try {
        const data = await apiFetch<HealthStatus>(path);
        if (data.status !== "ok") {
          stackStatusConsoleError("GET /health returned non-ok status", {
            url,
            VITE_API_BASE: import.meta.env.VITE_API_BASE ?? "(unset)",
            body: data,
          });
        } else {
          stackStatusConsoleDebug("GET /health OK (API strip green)", { url });
        }
        return data;
      } catch (err) {
        stackStatusConsoleError("GET /health failed (API strip red)", {
          url,
          VITE_API_BASE: import.meta.env.VITE_API_BASE ?? "(unset)",
          hint:
            "Wrong origin or missing /api proxy: open via Caddy :80 / :8880 or fix vite preview proxy for VITE_API_BASE=/api.",
          error: err instanceof Error ? err.message : String(err),
        });
        throw err;
      }
    },
    refetchInterval: 30_000,
  });
}

export function useCapabilities() {
  return useQuery<Capabilities>({
    queryKey: ["capabilities"],
    queryFn: () => apiFetch<Capabilities>("/capabilities"),
    staleTime: 5 * 60 * 1000,
  });
}
