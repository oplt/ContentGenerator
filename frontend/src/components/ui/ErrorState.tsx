export function ErrorState({ message }: { message: string }) {
  return (
    <div
      className="border border-destructive/30 bg-destructive/10 p-6 text-sm text-destructive"
      style={{ borderRadius: "var(--radius-card)" }}
    >
      {message}
    </div>
  );
}
