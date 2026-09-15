import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

/** URL-deep-linkable tab state that keeps sibling form state alive in the parent. */
export function useDeepLinkTab<T extends string>(
  param: string,
  allowed: readonly T[],
  fallback: T
): [T, (value: T) => void] {
  const [searchParams, setSearchParams] = useSearchParams();
  const raw = searchParams.get(param);
  const value = allowed.includes(raw as T) ? (raw as T) : fallback;

  const setValue = useCallback(
    (next: T) => {
      setSearchParams(
        (prev) => {
          const params = new URLSearchParams(prev);
          if (next === fallback) {
            params.delete(param);
          } else {
            params.set(param, next);
          }
          return params;
        },
        { replace: true }
      );
    },
    [fallback, param, setSearchParams]
  );

  return [value, setValue];
}
