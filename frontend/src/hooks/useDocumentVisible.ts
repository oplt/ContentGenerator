import { useSyncExternalStore } from "react";
import { isDocumentVisible } from "../lib/polling";

function subscribe(onStoreChange: () => void) {
  document.addEventListener("visibilitychange", onStoreChange);
  window.addEventListener("focus", onStoreChange);
  window.addEventListener("blur", onStoreChange);
  return () => {
    document.removeEventListener("visibilitychange", onStoreChange);
    window.removeEventListener("focus", onStoreChange);
    window.removeEventListener("blur", onStoreChange);
  };
}

/** Re-render when the document visibility changes so refetch intervals can resume. */
export function useDocumentVisible(): boolean {
  return useSyncExternalStore(subscribe, isDocumentVisible, () => true);
}
