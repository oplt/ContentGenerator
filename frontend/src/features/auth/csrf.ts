/** CSRF token helpers for cross-origin / stay-logged-in bootstrap. */

const CSRF_COOKIE = "csrf_token";
const CSRF_STORAGE_KEY = "sf_csrf_token";

function readDocumentCookie(name: string): string | null {
  if (typeof document === "undefined" || typeof document.cookie !== "string") {
    return null;
  }
  const match = document.cookie
    .split("; ")
    .find((item) => item.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=")[1] ?? "") : null;
}

export function getCsrfToken(): string | null {
  return (
    readDocumentCookie(CSRF_COOKIE) ||
    (typeof localStorage !== "undefined" ? localStorage.getItem(CSRF_STORAGE_KEY) : null) ||
    (typeof sessionStorage !== "undefined" ? sessionStorage.getItem(CSRF_STORAGE_KEY) : null)
  );
}

export function persistCsrfToken(token: string | null | undefined, rememberMe = true): void {
  if (!token || typeof window === "undefined") {
    return;
  }
  if (rememberMe) {
    localStorage.setItem(CSRF_STORAGE_KEY, token);
    sessionStorage.removeItem(CSRF_STORAGE_KEY);
  } else {
    sessionStorage.setItem(CSRF_STORAGE_KEY, token);
    localStorage.removeItem(CSRF_STORAGE_KEY);
  }
}

export function clearCsrfToken(): void {
  if (typeof window === "undefined") {
    return;
  }
  localStorage.removeItem(CSRF_STORAGE_KEY);
  sessionStorage.removeItem(CSRF_STORAGE_KEY);
}
