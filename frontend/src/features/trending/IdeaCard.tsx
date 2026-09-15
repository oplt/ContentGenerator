import { Sparkles } from "lucide-react";
import type { ProductIdea } from "../../api/trending";

export type IdeaCardProps = {
 idea: ProductIdea;
 index: number;
};

export function IdeaCard({ idea, index }: IdeaCardProps) {
 const scoreEntries = [
 ["Revenue", idea.scores.revenue_potential],
 ["Urgency", idea.scores.customer_urgency],
 ["Leverage", idea.scores.repo_leverage],
 ["MVP", idea.scores.speed_to_mvp],
 ] as const;

 return (
 <div className="bg-muted p-4 flex flex-col gap-2" style={{ borderRadius: "var(--radius-sm)" }}>
 <div className="flex items-baseline gap-2">
 <span className="text-xs text-muted-foreground">#{idea.rank || index}</span>
 <h3 className="text-sm font-normal text-foreground">{idea.title}</h3>
 </div>

 {idea.positioning && (
 <p className="text-xs text-primary italic leading-relaxed">{idea.positioning}</p>
 )}

 <p className="text-xs text-muted-foreground leading-relaxed">{idea.pain_point}</p>

 <p className="text-xs text-foreground leading-relaxed">{idea.product_concept}</p>

 {idea.why_this_repo_fits && (
 <p className="text-xs text-foreground/80 leading-relaxed">
 Why this repo fits: {idea.why_this_repo_fits}
 </p>
 )}

 <div className="grid grid-cols-2 gap-2 pt-1">
 {scoreEntries.map(([label, score]) => (
 <div
 key={label}
 className="border border-border px-2 py-1"
 style={{ borderRadius: "var(--radius-sm)" }}
 >
 <div className="text-[10px] font-medium text-muted-foreground">{label}</div>
 <div className="text-sm text-foreground">{score}/10</div>
 </div>
 ))}
 </div>

 <div className="mt-auto pt-2 border-t border-border flex flex-col gap-1">
 {idea.target_customer && (
 <div className="flex items-start gap-1.5 text-xs">
 <span className="text-muted-foreground shrink-0">Audience:</span>
 <span className="text-foreground">{idea.target_customer}</span>
 </div>
 )}
 {idea.monetization.model && (
 <div className="flex items-start gap-1.5 text-xs">
 <span className="text-muted-foreground shrink-0">Model:</span>
 <span className="text-foreground">{idea.monetization.model}</span>
 </div>
 )}
 {idea.monetization.pricing_logic && (
 <div className="flex items-start gap-1.5 text-xs">
 <span className="text-muted-foreground shrink-0">Pricing:</span>
 <span className="text-foreground">{idea.monetization.pricing_logic}</span>
 </div>
 )}
 {idea.time_to_mvp && (
 <div className="flex items-start gap-1.5 text-xs">
 <span className="text-muted-foreground shrink-0">Time:</span>
 <span className="text-foreground">{idea.time_to_mvp}</span>
 </div>
 )}
 {idea.why_now && (
 <div className="flex items-start gap-1.5 text-xs mt-1">
 <Sparkles className="size-3 text-primary shrink-0 mt-0.5" />
 <span className="text-primary italic">{idea.why_now}</span>
 </div>
 )}
 </div>
 </div>
 );
}
