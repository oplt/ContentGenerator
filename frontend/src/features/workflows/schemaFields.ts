/** Parse workflow node JSON Schema into renderable field descriptors (Phase 13). */

export type FieldKind =
  | "string"
  | "textarea"
  | "integer"
  | "number"
  | "boolean"
  | "enum"
  | "string_array"
  | "json";

export type SchemaField = {
  name: string;
  kind: FieldKind;
  title: string;
  description?: string;
  required: boolean;
  enumValues?: string[];
  defaultValue?: unknown;
};

type JsonSchema = {
  type?: string | string[];
  title?: string;
  description?: string;
  default?: unknown;
  enum?: unknown[];
  anyOf?: JsonSchema[];
  oneOf?: JsonSchema[];
  items?: JsonSchema;
  properties?: Record<string, JsonSchema>;
  required?: string[];
  minimum?: number;
  maximum?: number;
  minLength?: number;
  format?: string;
};

function unwrapNullable(schema: JsonSchema): JsonSchema {
  const alts = schema.anyOf ?? schema.oneOf;
  if (!alts?.length) return schema;
  const nonNull = alts.filter((item) => item.type !== "null");
  if (nonNull.length === 1) return { ...schema, ...nonNull[0], anyOf: undefined, oneOf: undefined };
  return schema;
}

function primaryType(schema: JsonSchema): string | undefined {
  const unwrapped = unwrapNullable(schema);
  if (Array.isArray(unwrapped.type)) {
    return unwrapped.type.find((t) => t !== "null");
  }
  return unwrapped.type;
}

function enumValues(schema: JsonSchema): string[] | undefined {
  const unwrapped = unwrapNullable(schema);
  if (!Array.isArray(unwrapped.enum) || unwrapped.enum.length === 0) return undefined;
  if (unwrapped.enum.every((v) => typeof v === "string" || typeof v === "number" || typeof v === "boolean")) {
    return unwrapped.enum.map(String);
  }
  return undefined;
}

export function resolveFieldKind(schema: JsonSchema): FieldKind {
  const unwrapped = unwrapNullable(schema);
  const values = enumValues(unwrapped);
  if (values) return "enum";

  const t = primaryType(unwrapped);
  if (t === "boolean") return "boolean";
  if (t === "integer") return "integer";
  if (t === "number") return "number";
  if (t === "array") {
    const itemType = primaryType(unwrapped.items ?? {});
    if (!itemType || itemType === "string" || itemType === "integer" || itemType === "number") {
      return "string_array";
    }
    return "json";
  }
  if (t === "object") return "json";
  if (t === "string") {
    const format = unwrapped.format ?? "";
    if (format === "textarea" || (typeof unwrapped.default === "string" && unwrapped.default.includes("\n"))) {
      return "textarea";
    }
    // Long-form hints from description / title
    const blob = `${unwrapped.title ?? ""} ${unwrapped.description ?? ""}`.toLowerCase();
    if (blob.includes("prompt") || blob.includes("text") || blob.includes("script") || blob.includes("body")) {
      return "textarea";
    }
    return "string";
  }
  // Unsupported / missing type → JSON fallback
  return "json";
}

export function parseConfigSchema(schema: Record<string, unknown> | null | undefined): SchemaField[] {
  if (!schema || typeof schema !== "object") return [];
  const root = schema as JsonSchema;
  const properties = root.properties ?? {};
  const required = new Set(root.required ?? []);
  return Object.entries(properties).map(([name, raw]) => {
    const prop = (raw ?? {}) as JsonSchema;
    const kind = resolveFieldKind(prop);
    return {
      name,
      kind,
      title: prop.title || name.replace(/_/g, " "),
      description: prop.description,
      required: required.has(name),
      enumValues: enumValues(prop),
      defaultValue: prop.default,
    };
  });
}

export function defaultConfigFromSchema(schema: Record<string, unknown> | null | undefined): Record<string, unknown> {
  const fields = parseConfigSchema(schema);
  const out: Record<string, unknown> = {};
  for (const field of fields) {
    if (field.defaultValue !== undefined) {
      out[field.name] = field.defaultValue;
    }
  }
  return out;
}

export function coerceFieldValue(kind: FieldKind, raw: unknown): unknown {
  if (kind === "boolean") return Boolean(raw);
  if (kind === "integer") {
    const n = typeof raw === "number" ? raw : Number.parseInt(String(raw ?? ""), 10);
    return Number.isFinite(n) ? n : 0;
  }
  if (kind === "number") {
    const n = typeof raw === "number" ? raw : Number.parseFloat(String(raw ?? ""));
    return Number.isFinite(n) ? n : 0;
  }
  if (kind === "string_array") {
    if (Array.isArray(raw)) return raw.map(String);
    if (typeof raw === "string") {
      return raw
        .split(/[\n,]/)
        .map((s) => s.trim())
        .filter(Boolean);
    }
    return [];
  }
  if (kind === "json") {
    if (typeof raw === "string") {
      try {
        return JSON.parse(raw) as unknown;
      } catch {
        return raw;
      }
    }
    return raw ?? {};
  }
  if (raw === null || raw === undefined) return "";
  return String(raw);
}

/** Map backend validate-config error strings onto field names when possible. */
export function mapConfigErrorsToFields(
  errors: string[],
  fieldNames: string[],
): Record<string, string> {
  const mapped: Record<string, string> = {};
  const names = new Set(fieldNames);
  for (const error of errors) {
    let assigned = false;
    for (const name of names) {
      if (error.includes(`'${name}'`) || error.includes(`"${name}"`) || error.includes(`${name}`)) {
        // Prefer exact token boundaries
        const re = new RegExp(`\\b${name}\\b`, "i");
        if (re.test(error)) {
          mapped[name] = mapped[name] ? `${mapped[name]}; ${error}` : error;
          assigned = true;
          break;
        }
      }
    }
    if (!assigned) {
      mapped._form = mapped._form ? `${mapped._form}; ${error}` : error;
    }
  }
  return mapped;
}
