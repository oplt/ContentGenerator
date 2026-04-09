import { useMutation, useQuery } from "@tanstack/react-query";
import { getConnectedAccounts, getSocialAccounts, validateConnectedAccount } from "../api/publishing";
import { queryClient } from "../lib/queryClient";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { LoadingState } from "../components/ui/LoadingState";

export default function ConnectedAccountsPage() {
  const connected = useQuery({ queryKey: ["publishing", "connected-accounts"], queryFn: getConnectedAccounts });
  const social = useQuery({ queryKey: ["publishing", "social-accounts"], queryFn: getSocialAccounts });
  const validateMutation = useMutation({
    mutationFn: validateConnectedAccount,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["publishing", "connected-accounts"] }),
        queryClient.invalidateQueries({ queryKey: ["publishing", "social-accounts"] }),
      ]);
    },
  });

  if (connected.isLoading || social.isLoading) {
    return <LoadingState label="Loading connected accounts" />;
  }

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <h1 className="text-2xl font-semibold">Connected Accounts</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Validate publishing auth state and inspect capability coverage for every connected platform.
        </p>
      </Card>

      <div className="grid gap-4">
        {(connected.data ?? []).map((account) => {
          const socialAccount = (social.data ?? []).find((item) => item.id === account.social_account_id);
          return (
            <Card key={account.id} className="p-5">
              <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                <div>
                  <h2 className="text-lg font-semibold capitalize">{account.platform}</h2>
                  <p className="text-sm text-muted-foreground">{account.account_name}</p>
                  <p className="mt-1 text-xs uppercase tracking-[0.16em] text-muted-foreground">
                    Auth: {account.auth_type} · Status: {account.status}
                  </p>
                  {socialAccount && (
                    <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
                      {Object.entries(socialAccount.capability_flags).map(([key, value]) => (
                        <span key={key} className="rounded-full border px-2 py-1">
                          {key}: {value}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <Button
                  variant="outline"
                  onClick={() => validateMutation.mutate(account.id)}
                  disabled={validateMutation.isPending}
                >
                  Validate Auth
                </Button>
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
