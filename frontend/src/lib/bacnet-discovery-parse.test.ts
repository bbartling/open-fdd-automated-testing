import { describe, expect, it } from "vitest";
import {
  extractPointDiscoveryObjects,
  extractWhoisDevices,
  parseDeviceInstanceFromIAmIdentifier,
  parseDeviceInstanceFromWhoisRow,
} from "./bacnet-discovery-parse";
import type { PointDiscoveryResponse, WhoIsResponse } from "./crud-api";

describe("parseDeviceInstanceFromIAmIdentifier", () => {
  it("parses device:instance", () => {
    expect(parseDeviceInstanceFromIAmIdentifier("device:12345")).toBe(12345);
  });
  it("accepts BACnet device id 0 (lower bound)", () => {
    expect(parseDeviceInstanceFromIAmIdentifier("device:0")).toBe(0);
  });
  it("accepts BACnet device id 4194303 (upper bound)", () => {
    expect(parseDeviceInstanceFromIAmIdentifier("device:4194303")).toBe(4194303);
  });
  it("parses device,instance", () => {
    expect(parseDeviceInstanceFromIAmIdentifier("device,999")).toBe(999);
  });
  it("falls back to last plausible number", () => {
    expect(parseDeviceInstanceFromIAmIdentifier("object 12 device 4000")).toBe(4000);
  });
  it("returns null for empty", () => {
    expect(parseDeviceInstanceFromIAmIdentifier("")).toBeNull();
  });
  it("returns null for out of range", () => {
    expect(parseDeviceInstanceFromIAmIdentifier("device:99999999")).toBeNull();
  });
});

describe("parseDeviceInstanceFromWhoisRow", () => {
  it("uses i-am-device-identifier", () => {
    expect(
      parseDeviceInstanceFromWhoisRow({
        "i-am-device-identifier": "device:42",
        "device-address": "1:2:3",
      }),
    ).toBe(42);
  });
});

describe("extractWhoisDevices", () => {
  it("reads devices from nested result.data", () => {
    const res: WhoIsResponse = {
      body: { result: { data: { devices: [{ "i-am-device-identifier": "device:1" }] } } },
    };
    expect(extractWhoisDevices(res)).toHaveLength(1);
  });

  it("treats mis-encoded string `devices` as empty (gateway bug / legacy payload)", () => {
    const res = {
      body: {
        result: {
          data: {
            devices: "No response(s) on WhoIs start_instance 1 end_instance 4194303",
          },
        },
      },
    } as WhoIsResponse;
    expect(extractWhoisDevices(res)).toEqual([]);
  });

  it("reads devices from top-level body array", () => {
    const res: WhoIsResponse = {
      body: [{ "i-am-device-identifier": "device:2" }] as unknown as Record<string, unknown>,
    };
    expect(extractWhoisDevices(res)).toHaveLength(1);
  });

  it("reads devices from object map of rows", () => {
    const res: WhoIsResponse = {
      body: {
        result: {
          data: {
            devices: {
              a: { "i-am-device-identifier": "device:3" },
              b: { "i-am-device-identifier": "device:4" },
            },
          },
        },
      },
    };
    const rows = extractWhoisDevices(res);
    expect(rows).toHaveLength(2);
    expect(rows.map((r) => r["i-am-device-identifier"]).sort()).toEqual(["device:3", "device:4"]);
  });
});

describe("extractPointDiscoveryObjects", () => {
  it("maps objects array", () => {
    const res: PointDiscoveryResponse = {
      body: {
        result: {
          data: {
            objects: [{ object_identifier: "analogInput:1", name: "SAT", commandable: false }],
          },
        },
      },
    };
    const rows = extractPointDiscoveryObjects(res);
    expect(rows).toEqual([
      { object_identifier: "analogInput:1", name: "SAT", commandable: false },
    ]);
  });
});
