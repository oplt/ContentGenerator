import { Button } from "./button";

export function ErrorState({
  message,
  title = "Something went wrong",
  onRetry,
  retryLabel = "Retry",
}: {
  message: string;
  title?: string;
  onRetry?: () => void;
  retryLabel?: string;
}) {
  return (
    <div
      role="alert"
      className="border border-destructive/30 bg-destructive/10 p-6 text-sm text-destructive"
      style={{ borderRadius: "var(--radius-card)" }}
    >
      <h2 className="text-base font-medium text-destructive">{title}</h2>
      <p className="mt-2">{message}</p>
      {onRetry ? (
        <Button type="button" variant="outline" className="mt-4" onClick={onRetry}>
          {retryLabel}
        </Button>
      ) : null}
    </div>
  );
}
