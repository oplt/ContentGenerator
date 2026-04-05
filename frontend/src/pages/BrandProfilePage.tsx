import { useMutation, useQuery } from "@tanstack/react-query";
import { getBrandProfile, upsertBrandProfile } from "../api/content";
import { queryClient } from "../lib/queryClient";
import { BrandProfileForm } from "../components/dashboard/BrandProfileForm";
import { LoadingState } from "../components/ui/LoadingState";

export default function BrandProfilePage() {
  const profile = useQuery({ queryKey: ["brand-profile"], queryFn: getBrandProfile });
  const mutation = useMutation({
    mutationFn: upsertBrandProfile,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["brand-profile"] });
    },
  });

  if (profile.isLoading || !profile.data) {
    return <LoadingState label="Loading brand profile" />;
  }

  return (
    <BrandProfileForm
      defaultValues={{
        name: profile.data.name,
        niche: profile.data.niche,
        tone: profile.data.tone,
        audience: profile.data.audience,
        default_cta: profile.data.default_cta ?? "",
        voice_notes: profile.data.voice_notes ?? "",
      }}
      onSubmit={async (values) => mutation.mutateAsync(values)}
    />
  );
}
