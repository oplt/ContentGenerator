import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "../ui/button";
import { Card } from "../ui/card";
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

  return (
    <Card className="p-6">
      <form className="grid gap-4" onSubmit={form.handleSubmit(onSubmit)}>
        <Input placeholder="Brand name" {...form.register("name")} />
        <div className="grid gap-4 md:grid-cols-2">
          <Input placeholder="Niche" {...form.register("niche")} />
          <Input placeholder="Tone" {...form.register("tone")} />
        </div>
        <Textarea placeholder="Audience" {...form.register("audience")} />
        <Input placeholder="Default CTA" {...form.register("default_cta")} />
        <Textarea placeholder="Voice notes" {...form.register("voice_notes")} />
        <Button type="submit">Save Brand Profile</Button>
      </form>
    </Card>
  );
}
