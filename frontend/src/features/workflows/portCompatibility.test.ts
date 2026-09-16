import { describe, expect, it } from "vitest";
import {
  DEFAULT_HANDLE_ID,
  findPort,
  normalizePortType,
  portsCompatible,
  typesCompatible,
} from "./portCompatibility";

describe("portCompatibility", () => {
  it("normalizes aliases", () => {
    expect(normalizePortType("Str")).toBe("string");
    expect(normalizePortType("list")).toBe("array");
  });

  it("accepts any/object and string↔uuid", () => {
    expect(typesCompatible("any", "number")).toBe(true);
    expect(typesCompatible("object", "string")).toBe(true);
    expect(typesCompatible("uuid", "string")).toBe(true);
    expect(typesCompatible("boolean", "string")).toBe(false);
  });

  it("finds ports by handle id", () => {
    const ports = [
      { name: "prompt", data_type: "string" },
      { name: "system_hint", data_type: "string" },
    ];
    expect(findPort(ports, "system_hint")?.name).toBe("system_hint");
    expect(findPort(ports, DEFAULT_HANDLE_ID)?.name).toBe("prompt");
    expect(findPort([], "x")).toBeNull();
  });

  it("treats missing ports as compatible", () => {
    expect(portsCompatible(undefined, undefined)).toBe(true);
  });
});
