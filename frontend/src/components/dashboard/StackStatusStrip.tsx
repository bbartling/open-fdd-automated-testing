import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { useHealth } from "@/hooks/use-fdd-status";
import { useBacnetStatus } from "@/hooks/use-bacnet-status";
import { getDriverProfileStatus } from "@/lib/crud-api";
import { stackStatusConsoleWarn } from "@/lib/stack-status-console";
import { cn } from "@/lib/utils";

type Status = "green" | "yellow" | "red" | "gray";

function StatusDot({ status, label, title }: { status: Status; label: string; title?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium",
        status === "green" && "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
        status === "yellow" && "bg-amber-500/15 text-amber-700 dark:text-amber-400",
        status === "red" && "bg-red-500/15 text-red-700 dark:text-red-400",
        status === "gray" && "bg-muted text-muted-foreground",
      )}
      title={title ?? label}
    >
      <span
        className={cn(
          "h-1.5 w-1.5 shrink-0 rounded-full",
          status === "green" && "bg-emerald-500",
          status === "yellow" && "bg-amber-500",
          status === "red" && "bg-red-500",
          status === "gray" && "bg-muted-foreground",
        )}
        aria-hidden
      />
      {label}
    </span>
  );
}

export function StackStatusStrip() {
  const { data: health, isError: healthError, isLoading: healthLoading } = useHealth();
  const { data: profile, isLoading: profileLoading, isError: profileError } = useQuery({
    queryKey: ["driver-profile"],
    queryFn: getDriverProfileStatus,
    retry: false,
  });
  // Fail closed: unless bootstrap profile explicitly says BACnet is enabled,
  // render BACnet as neutral gray and avoid noisy server_hello probes.
  const bacnetBootstrapped = profile?.drivers?.bacnet === true;
  const { data: bacnet, isError: bacnetError, isLoading: bacnetLoading } = useBacnetStatus(bacnetBootstrapped);

  const apiStatus: Status = healthLoading ? "gray" : healthError || health?.status !== "ok" ? "red" : "green";
  const result = bacnet?.body?.result;
  const mqtt = result?.mqtt_bridge;
  const bacnetStatus: Status = profileLoading
    ? "gray"
    : !bacnetBootstrapped
      ? "gray"
      : bacnetLoading
        ? "gray"
        : bacnetError || !bacnet?.ok
          ? "red"
          : "green";
  const mqttStatus: Status =
    !mqtt ? "gray" : mqtt.enabled && mqtt.connected ? "green" : mqtt.enabled ? "yellow" : "gray";
  const bacnetDiagnostics = bacnet?.diagnostics;
  const bacnetTroubleshooting =
    bacnetBootstrapped && bacnetStatus === "red" && bacnetDiagnostics
      ? `BACnet gateway unreachable (${bacnetDiagnostics.errorCategory}). API target: ${
          bacnetDiagnostics.gatewayUrlTheApiUses ?? "unknown"
        }. Check Network tab: ${bacnetDiagnostics.checkInNetworkTab}`
      : null;

  const stripDegradedSig = useRef("");
  useEffect(() => {
    if (healthLoading || bacnetLoading) return;
    if (apiStatus !== "red" && (!bacnetBootstrapped || bacnetStatus !== "red")) {
      stripDegradedSig.current = "";
      return;
    }
    const sig = [
      apiStatus,
      bacnetStatus,
      bacnetBootstrapped ? "bootstrapped" : "not-bootstrapped",
      profileError ? "driver-profile-error" : "driver-profile-ok",
      mqttStatus,
      healthError,
      bacnetError,
      health?.status ?? "",
      bacnet?.ok === true ? "1" : bacnet?.ok === false ? "0" : "",
      bacnet?.error ?? "",
      bacnet?.status_code ?? "",
      JSON.stringify(bacnet?.body?.error ?? null),
    ].join("|");
    if (sig === stripDegradedSig.current) return;
    stripDegradedSig.current = sig;
    stackStatusConsoleWarn(
      "Stack strip degraded — useHealth / useBacnetStatus also emit [OpenFDD Stack] lines for each request",
      {
        apiStatus,
        bacnetStatus,
        mqttStatus,
        healthError,
        bacnetError,
        health: health ?? null,
        bacnetSummary: bacnet
          ? {
              ok: bacnet.ok,
              status_code: bacnet.status_code,
              error: bacnet.error,
              jsonrpc_error: bacnet.body?.error ?? null,
            }
          : null,
        VITE_API_BASE: import.meta.env.VITE_API_BASE ?? "(unset)",
      },
    );
  }, [
    apiStatus,
    bacnetStatus,
    bacnetBootstrapped,
    profileError,
    mqttStatus,
    healthLoading,
    profileLoading,
    bacnetLoading,
    healthError,
    bacnetError,
    health,
    bacnet,
  ]);

  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-border/40 bg-muted/20 px-6 py-2 text-sm">
      <span className="mr-1 text-muted-foreground">Stack:</span>
      <StatusDot
        status={apiStatus}
        label="API"
        title={apiStatus === "green" ? "API healthy" : apiStatus === "red" ? "API unreachable" : "Checking…"}
      />
      <StatusDot
        status={bacnetStatus}
        label="BACnet"
        title={
          !bacnetBootstrapped
            ? "BACnet not bootstrapped (disabled in driver profile)"
            : bacnetStatus === "green"
            ? "BACnet gateway OK"
            : bacnetStatus === "red"
              ? "BACnet gateway unreachable"
              : "Checking…"
        }
      />
      <StatusDot
        status={mqttStatus}
        label="MQTT bridge"
        title={
          mqttStatus === "green"
            ? mqtt?.broker_url
              ? `Connected to ${mqtt.broker_url}`
              : "Connected"
            : mqttStatus === "yellow"
              ? mqtt?.last_error
                ? `Disconnected: ${mqtt.last_error}`
                : "Enabled but disconnected"
              : "Not enabled or no bridge"
        }
      />
      {bacnetTroubleshooting ? (
        <span className="ml-1 text-xs text-red-700 dark:text-red-400">{bacnetTroubleshooting}</span>
      ) : null}
    </div>
  );
}
