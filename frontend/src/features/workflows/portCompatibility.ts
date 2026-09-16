/** Client-side port type compatibility (mirrors backend compiler_checks.types_compatible). */

import type { WorkflowNodePort } from "../../api/workflows";

const ALIASES: Record<string, string> = {
  str: "string",
  text: "string",
  int: "number",
  float: "number",
  bool: "boolean",
  list: "array",
};

export function normalizePortType(raw: string): string {
  const key = raw.trim().toLowerCase();
  return ALIASES[key] ?? key;
}

export function typesCompatible(sourceType: string, targetType: string): boolean {
  const src = normalizePortType(sourceType);
  const dst = normalizePortType(targetType);
  if (src === "any" || src === "object" || dst === "any" || dst === "object") return true;
  if (src === dst) return true;
  if (["string", "uuid"].includes(src) && ["string", "uuid"].includes(dst)) {
    return true;
  }
  if (src === "array" && dst.startsWith("array")) return true;
  return false;
}

export function portsCompatible(
  source: WorkflowNodePort | null | undefined,
  target: WorkflowNodePort | null | undefined,
): boolean {
  if (!source || !target) return true; // untyped / default handles
  return typesCompatible(source.data_type, target.data_type);
}

export const DEFAULT_HANDLE_ID = "__default__";

export function findPort(
  ports: WorkflowNodePort[] | undefined,
  handleId: string | null | undefined,
): WorkflowNodePort | null {
  if (!ports?.length) return null;
  if (!handleId || handleId === DEFAULT_HANDLE_ID) return ports[0] ?? null;
  return ports.find((p) => p.name === handleId) ?? null;
}
