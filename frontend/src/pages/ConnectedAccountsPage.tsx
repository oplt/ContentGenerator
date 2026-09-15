import { useMutation, useQuery } from "@tanstack/react-query";
import {
  getConnectedAccounts,
  getSocialAccounts,
  validateConnectedAccount,
} from "../api/publishing";
import { SocialAccountConnectionCard } from "../components/dashboard/SocialAccountConnectionCard";
import { SocialAccountSelector } from "../components/dashboard/SocialAccountSelector";
import { Card } from "../components/ui/card";
import { LoadingState } from "../components/ui/LoadingState";
import { useAccountSelection } from "../hooks/useAccountSelection";
import { useTenantScope } from "../hooks/useTenantScope";
import { queryClient } from "../lib/queryClient";
import { queryKeys } from "../lib/queryKeys";

export default function ConnectedAccountsPage() {
  const { tenantId, enabled } = useTenantScope();
  const { selectedIds, setSelectedIds, toggle } = useAccountSelection(tenantId);
  const connected = useQuery({
    queryKey: queryKeys.connectedAccounts(tenantId ?? "none"),
    queryFn: getConnectedAccounts,
    enabled,
  });
  const social = useQuery({
    queryKey: queryKeys.socialAccounts(tenantId ?? "none"),
    queryFn: getSocialAccounts,
    enabled,
  });
  const validateMutation = useMutation({
    mutationFn: validateConnectedAccount,
    onSuccess: async () => {
      if (!tenantId) return;
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.connectedAccounts(tenantId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.socialAccounts(tenantId) }),
      ]);
    },
  });

  if (connected.isLoading || social.isLoading) {
    return <LoadingState label="Loading connected accounts" />;
  }

  const accounts = social.data ?? [];
  const connectedBySocialId = new Map(
    (connected.data ?? [])
      .filter((item) => item.social_account_id)
      .map((item) => [item.social_account_id as string, item])
  );

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <h1 className="text-2xl font-semibold">Connected Accounts</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Manage publish destinations by account ID. Selection carries into Content generation and
          Publishing so two accounts on the same platform stay distinct.
        </p>
      </Card>

      <Card className="p-6">
        <SocialAccountSelector
          accounts={accounts}
          selectedIds={selectedIds}
          onChange={setSelectedIds}
          label="Default selection for generate & publish"
        />
      </Card>

      <div className="grid gap-4">
        {accounts.length === 0 ? (
          <Card className="p-5">
            <p className="text-sm text-muted-foreground">
              No social accounts yet. Connect platforms from Settings to create account identities.
            </p>
          </Card>
        ) : (
          accounts.map((account) => {
            const projection = connectedBySocialId.get(account.id);
            return (
              <SocialAccountConnectionCard
                key={account.id}
                account={account}
                selected={selectedIds.includes(account.id)}
                onSelectToggle={toggle}
                connectedAccountId={projection?.id}
                onValidate={projection ? (id) => validateMutation.mutate(id) : undefined}
                validatePending={validateMutation.isPending}
              />
            );
          })
        )}
      </div>
    </div>
  );
}
