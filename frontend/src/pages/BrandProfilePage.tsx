import { useMutation, useQuery } from "@tanstack/react-query";
import { getBrandProfile, upsertBrandProfile } from "../api/content";
import { useTenantScope } from "../hooks/useTenantScope";
import { queryClient } from "../lib/queryClient";
import { queryKeys } from "../lib/queryKeys";
import { BrandProfileForm } from "../components/dashboard/BrandProfileForm";
import { SectionHelp } from "../components/ui/HelpDisclosure";
import { QueryBoundary } from "../components/ui/QueryBoundary";

export default function BrandProfilePage() {
  const { tenantId, enabled } = useTenantScope();
  const profile = useQuery({
    queryKey: queryKeys.brandProfile(tenantId ?? "none"),
    queryFn: getBrandProfile,
    enabled,
  });
  const mutation = useMutation({
    mutationFn: upsertBrandProfile,
    onSuccess: async () => {
      if (!tenantId) return;
      await queryClient.invalidateQueries({ queryKey: queryKeys.brandProfile(tenantId) });
    },
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Brand profile</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Voice, audience, and guardrails used when generating briefs and assets.
        </p>
      </div>
      <SectionHelp summary="Why brand profile matters">
        Content plans and editorial briefs inherit tone, CTA, and risk tolerance from this profile. Saving overwrites
        the workspace default—keep destructive or legal constraints in guardrails, not in optional notes.
      </SectionHelp>
      {mutation.isError ? (
        <p className="text-sm text-destructive" role="alert">
          Brand profile could not be saved. Check required fields and try again.
        </p>
      ) : null}
      <QueryBoundary
        query={profile}
        loadingLabel="Loading brand profile"
        errorMessage="Brand profile could not be loaded."
      >
        {(data) => (
          <BrandProfileForm
            defaultValues={{
              name: data.name,
              niche: data.niche,
              tone: data.tone,
              audience: data.audience,
              default_cta: data.default_cta ?? "",
              voice_notes: data.voice_notes ?? "",
            }}
            onSubmit={async (values) => mutation.mutateAsync(values)}
          />
        )}
      </QueryBoundary>
    </div>
  );
}
