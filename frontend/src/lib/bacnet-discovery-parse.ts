import type { PointDiscoveryResponse, WhoIsResponse } from "@/lib/crud-api";

/** Row shape from diy-bacnet-server `perform_who_is` (client_utils). */
export type WhoisDeviceRow = {
  "i-am-device-identifier"?: string;
  "device-address"?: string;
  "device-description"?: string;
  [key: string]: unknown;
};

/**
 * Parse BACnet device instance from Who-Is `i-am-device-identifier` string
 * (e.g. bacpypes `device:12345` / `device,12345`).
 */
export function parseDeviceInstanceFromIAmIdentifier(raw: string): number | null {
  const s = (raw || "").trim();
  if (!s) return null;
  const dm = s.match(/device\D*(\d+)/i);
  if (dm) {
    const n = Number(dm[1]);
    if (Number.isFinite(n) && n >= 0 && n <= 4194303) return n;
  }
  const nums = s.match(/\d+/g);
  if (!nums?.length) return null;
  for (let i = nums.length - 1; i >= 0; i--) {
    const n = Number(nums[i]);
    if (Number.isFinite(n) && n >= 0 && n <= 4194303) return n;
  }
  return null;
}

export function parseDeviceInstanceFromWhoisRow(row: WhoisDeviceRow): number | null {
  return parseDeviceInstanceFromIAmIdentifier(row["i-am-device-identifier"] ?? "");
}

export function extractWhoisDevices(res: WhoIsResponse): WhoisDeviceRow[] {
  const body = res?.body ?? res;
  if (Array.isArray(body)) {
    return body as WhoisDeviceRow[];
  }
  const data =
    (body as { result?: { data?: { devices?: unknown }; devices?: unknown } })?.result?.data ??
    (body as { devices?: unknown; data?: { devices?: unknown } })?.data ??
    (body as { devices?: unknown });
  const devicesRaw = data?.devices ?? (Array.isArray(data) ? data : null);
  if (Array.isArray(devicesRaw)) {
    return devicesRaw as WhoisDeviceRow[];
  }
  if (devicesRaw && typeof devicesRaw === "object") {
    const vals = Object.values(devicesRaw as Record<string, unknown>);
    if (vals.length && vals.every((v) => v && typeof v === "object" && !Array.isArray(v))) {
      return vals as WhoisDeviceRow[];
    }
  }
  // Mis-encoded gateway payloads (e.g. error string in `devices`) must never crash the UI.
  return [];
}

export type PointDiscoveryObjectRow = {
  object_identifier: string;
  name: string;
  commandable: boolean;
};

export function extractPointDiscoveryObjects(res: PointDiscoveryResponse): PointDiscoveryObjectRow[] {
  const body = res?.body ?? res;
  const result = (body as { result?: { data?: { objects?: unknown[] }; objects?: unknown[] } })?.result;
  const data = result?.data ?? result;
  const objects = (data?.objects ?? []) as {
    object_identifier?: string;
    name?: string;
    commandable?: boolean;
  }[];
  return objects.map((o) => ({
    object_identifier: o.object_identifier ?? "—",
    name: o.name ?? "—",
    commandable: o.commandable ?? false,
  }));
}
