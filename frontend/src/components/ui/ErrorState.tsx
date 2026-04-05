export function ErrorState({ message }: { message: string }) {
  return (
    <div className="rounded-[1.5rem] border border-destructive/30 bg-destructive/10 p-6 text-sm text-destructive">
      {message}
    </div>
  );
}
