import { useCallback, useEffect, useState } from "react";

const storageKey = (tenantId: string) => `cg:selected-social-accounts:${tenantId}`;

function readStored(tenantId: string | null): string[] {
  if (!tenantId || typeof window === "undefined") return [];
  try {
    const raw = window.sessionStorage.getItem(storageKey(tenantId));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item): item is string => typeof item === "string");
  } catch {
    return [];
  }
}

/**
 * Persist selected social account IDs per tenant across Content / Publishing navigation.
 */
export function useAccountSelection(tenantId: string | null) {
  const [selectedIds, setSelectedIdsState] = useState<string[]>(() => readStored(tenantId));

  useEffect(() => {
    setSelectedIdsState(readStored(tenantId));
  }, [tenantId]);

  const setSelectedIds = useCallback(
    (next: string[] | ((prev: string[]) => string[])) => {
      setSelectedIdsState((prev) => {
        const resolved = typeof next === "function" ? next(prev) : next;
        const unique = Array.from(new Set(resolved));
        if (tenantId && typeof window !== "undefined") {
          window.sessionStorage.setItem(storageKey(tenantId), JSON.stringify(unique));
        }
        return unique;
      });
    },
    [tenantId]
  );

  const toggle = useCallback(
    (accountId: string) => {
      setSelectedIds((prev) =>
        prev.includes(accountId) ? prev.filter((id) => id !== accountId) : [...prev, accountId]
      );
    },
    [setSelectedIds]
  );

  const clear = useCallback(() => setSelectedIds([]), [setSelectedIds]);

  return { selectedIds, setSelectedIds, toggle, clear };
}
