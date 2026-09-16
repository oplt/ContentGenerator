import { describe, expect, it } from "vitest";
import {
  coerceFieldValue,
  defaultConfigFromSchema,
  mapConfigErrorsToFields,
  parseConfigSchema,
  resolveFieldKind,
} from "./schemaFields";

describe("schemaFields", () => {
  it("parses generate_text-like config schema kinds", () => {
    const fields = parseConfigSchema({
      type: "object",
      properties: {
        max_tokens: { type: "integer", default: 800, title: "Max tokens" },
        temperature: { type: "number", default: 0.7 },
        task: { type: "string", default: "default" },
        tone: { anyOf: [{ type: "string" }, { type: "null" }] },
        dry_run: { type: "boolean", default: true },
        platforms: { type: "array", items: { type: "string" } },
        mode: { type: "string", enum: ["stub", "live"] },
        nested: { type: "object", properties: { a: { type: "string" } } },
      },
      required: ["task"],
    });
    const byName = Object.fromEntries(fields.map((f) => [f.name, f]));
    expect(byName.max_tokens?.kind).toBe("integer");
    expect(byName.temperature?.kind).toBe("number");
    expect(byName.tone?.kind).toBe("string");
    expect(byName.dry_run?.kind).toBe("boolean");
    expect(byName.platforms?.kind).toBe("string_array");
    expect(byName.mode?.kind).toBe("enum");
    expect(byName.mode?.enumValues).toEqual(["stub", "live"]);
    expect(byName.nested?.kind).toBe("json");
    expect(byName.task?.required).toBe(true);
  });

  it("seeds defaults from schema", () => {
    expect(
      defaultConfigFromSchema({
        properties: {
          dry_run: { type: "boolean", default: true },
          max_tokens: { type: "integer", default: 200 },
          other: { type: "string" },
        },
      }),
    ).toEqual({ dry_run: true, max_tokens: 200 });
  });

  it("coerces array and number values", () => {
    expect(coerceFieldValue("string_array", "a, b\nc")).toEqual(["a", "b", "c"]);
    expect(coerceFieldValue("integer", "12")).toBe(12);
    expect(coerceFieldValue("boolean", true)).toBe(true);
  });

  it("maps backend errors onto field names", () => {
    const mapped = mapConfigErrorsToFields(
      ["Value error, max_tokens must be <= 8000", "general failure"],
      ["max_tokens", "temperature"],
    );
    expect(mapped.max_tokens).toContain("max_tokens");
    expect(mapped._form).toContain("general failure");
  });

  it("treats prompt-like strings as textarea", () => {
    expect(resolveFieldKind({ type: "string", title: "Prompt" })).toBe("textarea");
  });
});
