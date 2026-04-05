import { Card } from "../components/ui/card";

export default function VerifyEmailPage() {
  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="max-w-lg p-8">
        <h1 className="text-2xl font-semibold">Verify Email</h1>
        <p className="mt-3 text-sm text-muted-foreground">
          Check your inbox for the verification link. The backend endpoint is wired and will validate the token when used.
        </p>
      </Card>
    </div>
  );
}
