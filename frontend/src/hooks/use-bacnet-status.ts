import { useQuery } from "@tanstack/react-query";
import { apiFetch, resolveApiUrl } from "@/lib/api";
import { stackStatusConsoleDebug, stackStatusConsoleError } from "@/lib/stack-status-console";
import type { BacnetServerHelloResponse } from "@/types/api";

/**
 * Request init used for POST /bacnet/server_hello.
 * Exported for unit tests so we can assert Content-Type and method are set correctly.
 * Without Content-Type: application/json the Open-FDD API returns 422 and the BACnet status dot stays red.
 */
export const SERVER_HELLO_REQUEST_INIT: RequestInit = {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({}),
};

/** POST /bacnet/server_hello — returns gateway and mqtt_bridge status. */
export function useBacnetStatus() {
  return useQuery<BacnetServerHelloResponse>({
    queryKey: ["bacnet", "server_hello"],
    queryFn: async () => {
      const path = "/bacnet/server_hello";
      const url = resolveApiUrl(path);
      try {
        const data = await apiFetch<BacnetServerHelloResponse>(path, SERVER_HELLO_REQUEST_INIT);
        if (!data.ok) {
          stackStatusConsoleError(
            "POST /bacnet/server_hello returned ok: false (API could not reach the DIY BACnet gateway)",
            {
              openfddApiUrl: url,
              gatewayUrlTheApiUses: data.gateway_url ?? null,
              VITE_API_BASE: import.meta.env.VITE_API_BASE ?? "(unset)",
              topLevelError: data.error ?? null,
              jsonRpcError:
                data.body && typeof data.body === "object" && "error" in data.body ? data.body.error : null,
              statusCode: data.status_code ?? null,
              note:
                "openfddApiUrl is your browser→OpenFDD request. gatewayUrlTheApiUses is where the API container sends JSON-RPC (OFDD_BACNET_SERVER_URL overrides ofdd:bacnetServerUrl in Docker).",
              checkInNetworkTab: "GET /bacnet/gateways lists default gateway URLs the API will use.",
            },
          );
        } else {
          stackStatusConsoleDebug("POST /bacnet/server_hello OK (BACnet strip green)", {
            url,
            message: data.body?.result?.message ?? null,
          });
        }
        return data;
      } catch (err) {
        stackStatusConsoleError("POST /bacnet/server_hello failed (network, 401/403, 422 body, or bad JSON)", {
          url,
          VITE_API_BASE: import.meta.env.VITE_API_BASE ?? "(unset)",
          hint:
            "If you use raw :5173, vite preview must proxy /api with strip_prefix (see vite.config.ts). Prefer Caddy :80 or :8880.",
          error: err instanceof Error ? err.message : String(err),
        });
        throw err;
      }
    },
    staleTime: 30 * 1000,
    refetchInterval: 60 * 1000,
    retry: 1,
  });
}
