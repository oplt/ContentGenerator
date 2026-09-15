import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "../ui/button";
import { Card } from "../ui/card";
import { FormField } from "../ui/HelpDisclosure";
import { Input } from "../ui/input";
import { Textarea } from "../ui/textarea";

const schema = z.object({
  name: z.string().min(2),
  niche: z.string().min(2),
  tone: z.string().min(2),
  audience: z.string().min(2),
  default_cta: z.string().optional(),
  voice_notes: z.string().optional(),
});

type FormValues = z.infer<typeof schema>;

export function BrandProfileForm({
  defaultValues,
  onSubmit,
}: {
  defaultValues: FormValues;
  onSubmit: (values: FormValues) => Promise<unknown>;
}) {
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues,
  });
  const errors = form.formState.errors;

  return (
    <Card className="p-6">
      <form className="grid gap-4 md:grid-cols-2" onSubmit={form.handleSubmit(onSubmit)}>
        <FormField
          className="md:col-span-2"
          label="Brand name"
          htmlFor="brand-name"
          error={errors.name?.message}
        >
          <Input id="brand-name" placeholder="Brand name" {...form.register("name")} />
        </FormField>
        <FormField label="Niche" htmlFor="brand-niche" error={errors.niche?.message}>
          <Input id="brand-niche" placeholder="Niche" {...form.register("niche")} />
        </FormField>
        <FormField
          label="Tone"
          htmlFor="brand-tone"
          help="Voice used for briefs and generated assets."
          error={errors.tone?.message}
        >
          <Input id="brand-tone" placeholder="Tone" {...form.register("tone")} />
        </FormField>
        <FormField
          className="md:col-span-2"
          label="Audience"
          htmlFor="brand-audience"
          error={errors.audience?.message}
        >
          <Textarea id="brand-audience" placeholder="Audience" {...form.register("audience")} />
        </FormField>
        <FormField
          label="Default CTA"
          htmlFor="brand-cta"
          help="Primary call-to-action suggested in drafts."
        >
          <Input id="brand-cta" placeholder="Default CTA" {...form.register("default_cta")} />
        </FormField>
        <FormField
          label="Voice notes"
          htmlFor="brand-voice"
          help="Optional style notes. Keep legal/destructive constraints in guardrails, not here."
        >
          <Textarea id="brand-voice" placeholder="Voice notes" {...form.register("voice_notes")} />
        </FormField>
        <div className="md:col-span-2">
          <Button type="submit">Save Brand Profile</Button>
        </div>
      </form>
    </Card>
  );
}
