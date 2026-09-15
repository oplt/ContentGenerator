import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, GitFork, Sparkles, Star, TrendingUp, Twitter } from "lucide-react";
import {
 generateProductIdeas,
 generateTwitterPost,
 type TrendingRepo,
 type TrendingReposListResponse,
} from "../../api/trending";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { queryKeys } from "../../lib/queryKeys";
import { useWorkspaceStore } from "../../store/workspaceStore";
import { AssessmentList } from "./AssessmentList";
import { IdeaCard } from "./IdeaCard";
import { TwitterPostCard } from "./TwitterPostCard";

export type RepoCardProps = {
 repo: TrendingRepo;
};

export function RepoCard({ repo }: RepoCardProps) {
 const [showIdeas, setShowIdeas] = useState(false);
 const [generationError, setGenerationError] = useState<string | null>(null);
 const [showTwitterPanel, setShowTwitterPanel] = useState(false);
 const [twitterPost, setTwitterPost] = useState<string | null>(null);
 const [twitterError, setTwitterError] = useState<string | null>(null);
 const queryClient = useQueryClient();

 const ideasMutation = useMutation({
 mutationFn: () => generateProductIdeas(repo.id),
 onSuccess: async (updatedRepo) => {
 setGenerationError(null);
 setShowIdeas(true);
 queryClient.setQueriesData(
 { queryKey: queryKeys.trendingRepos(useWorkspaceStore.getState().tenantId ?? "none") },
 (existing: TrendingReposListResponse | undefined) => {
 if (!existing) {
 return existing;
 }
 return {
 ...existing,
 repos: existing.repos.map((existingRepo) =>
 existingRepo.id === updatedRepo.id ? updatedRepo : existingRepo,
 ),
 };
 },
 );
 const tenantId = useWorkspaceStore.getState().tenantId;
 if (tenantId) {
 await queryClient.invalidateQueries({ queryKey: queryKeys.trendingRepos(tenantId) });
 }
 },
 onError: (error) => {
 setGenerationError(error instanceof Error ? error.message : "Could not generate ideas.");
 },
 });

 const twitterMutation = useMutation({
 mutationFn: () => generateTwitterPost(repo.id),
 onSuccess: (data) => {
 setTwitterPost(data.post_text);
 setTwitterError(null);
 setShowTwitterPanel(true);
 },
 onError: (error) => {
 setTwitterError(error instanceof Error ? error.message : "Could not generate Twitter post.");
 },
 });

 const visibleIdeas =
 repo.product_ideas.length > 0 ? repo.product_ideas : (ideasMutation.data?.product_ideas ?? []);
 const visibleAssessment = repo.repo_assessment ?? ideasMutation.data?.repo_assessment ?? null;
 const hasIdeas = visibleIdeas.length > 0;

 return (
 <Card className="p-5">
 <div className="flex items-start gap-4">
 <div
 className="flex h-8 w-8 shrink-0 items-center justify-center bg-muted text-xs font-normal text-muted-foreground"
 style={{ borderRadius: "var(--radius-sm)" }}
 >
 #{repo.rank}
 </div>

 <div className="flex-1 min-w-0">
 <div className="flex flex-wrap items-center gap-2 mb-1">
 <a
 href={repo.html_url}
 target="_blank"
 rel="noopener noreferrer"
 className="text-base font-normal text-foreground hover:text-primary transition-colors flex items-center gap-1"
 >
 {repo.full_name}
 <ExternalLink className="size-3.5 shrink-0" />
 </a>
 {repo.language && <Badge variant="muted">{repo.language}</Badge>}
 </div>

 {repo.description && (
 <p className="text-sm text-muted-foreground line-clamp-2 mb-3">{repo.description}</p>
 )}

 {repo.topics.length > 0 && (
 <div className="flex flex-wrap gap-1.5 mb-3">
 {repo.topics.slice(0, 6).map((topic) => (
 <span
 key={topic}
 className="text-xs text-muted-foreground border border-border px-2 py-0.5"
 style={{ borderRadius: "var(--radius-sm)" }}
 >
 {topic}
 </span>
 ))}
 </div>
 )}

 <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
 <span className="flex items-center gap-1">
 <Star className="size-3.5 text-warning" />
 {repo.stars_count.toLocaleString()} stars
 </span>
 {repo.stars_gained > 0 && (
 <span className="flex items-center gap-1 text-success">
 <TrendingUp className="size-3.5" />
 +{repo.stars_gained.toLocaleString()} in period
 </span>
 )}
 <span className="flex items-center gap-1">
 <GitFork className="size-3.5" />
 {repo.forks_count.toLocaleString()} forks
 </span>
 {repo.ideas_generated_at && (
 <span className="text-muted-foreground/60">
 Ideas generated {new Date(repo.ideas_generated_at).toLocaleDateString()}
 </span>
 )}
 </div>
 </div>

 <div className="flex flex-col items-end gap-2 shrink-0">
 {!hasIdeas ? (
 <div className="flex flex-col items-end gap-2">
 <Button
 variant="outline"
 size="sm"
 onClick={() => ideasMutation.mutate()}
 disabled={ideasMutation.isPending}
 >
 <Sparkles className="size-3.5" />
 {ideasMutation.isPending ? "Generating…" : "Generate Ideas"}
 </Button>
 {ideasMutation.isError && (
 <p className="max-w-56 text-right text-[11px] font-medium text-destructive">
 {generationError ?? "Could not generate ideas."}
 </p>
 )}
 </div>
 ) : (
 <Button variant="ghost" size="sm" onClick={() => setShowIdeas((value) => !value)}>
 <Sparkles className="size-3.5 text-primary" />
 {showIdeas ? "Hide Ideas" : `${visibleIdeas.length} Ideas`}
 </Button>
 )}
 <div className="flex flex-col items-end gap-1">
 <Button
 variant="outline"
 size="sm"
 onClick={() => {
 if (twitterPost) {
 setShowTwitterPanel((value) => !value);
 } else {
 twitterMutation.mutate();
 }
 }}
 disabled={twitterMutation.isPending}
 >
 <Twitter className="size-3.5" />
 {twitterMutation.isPending
 ? "Generating…"
 : twitterPost
 ? showTwitterPanel
 ? "Hide Post"
 : "Show Post"
 : "Generate Twitter Post"}
 </Button>
 {twitterMutation.isError && (
 <p className="max-w-56 text-right text-[11px] font-medium text-destructive">
 {twitterError ?? "Could not generate post."}
 </p>
 )}
 </div>
 </div>
 </div>

 {showTwitterPanel && twitterPost && (
 <div className="mt-4 border-t border-border pt-4">
 <p className="text-xs font-medium text-muted-foreground mb-3">Twitter / X Post</p>
 <TwitterPostCard
 repoId={repo.id}
 initialText={twitterPost}
 onReject={() => setShowTwitterPanel(false)}
 />
 </div>
 )}

 {hasIdeas && showIdeas && (
 <div className="mt-4 border-t border-border pt-4">
 {visibleAssessment && (
 <div className="mb-4 grid gap-3 lg:grid-cols-[1.4fr_1fr]">
 <div className="bg-muted p-4" style={{ borderRadius: "var(--radius-sm)" }}>
 <div className="mb-2 flex items-center justify-between gap-2">
 <p className="text-xs font-medium text-muted-foreground">Repo Assessment</p>
 <Badge variant="muted">{visibleAssessment.confidence}</Badge>
 </div>
 <p className="text-sm text-foreground leading-relaxed">{visibleAssessment.what_it_does}</p>
 {visibleAssessment.best_commercial_angle && (
 <p className="mt-3 text-xs text-primary">
 Best angle: {visibleAssessment.best_commercial_angle}
 </p>
 )}
 </div>
 <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
 <AssessmentList label="Assets" items={visibleAssessment.strongest_assets} />
 <AssessmentList label="Limitations" items={visibleAssessment.main_limitations} />
 </div>
 </div>
 )}
 <p className="text-xs font-medium text-muted-foreground mb-3">
 AI-Generated Product Ideas
 </p>
 <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
 {visibleIdeas.map((idea, idx) => (
 <IdeaCard key={idx} idea={idea} index={idx + 1} />
 ))}
 </div>
 </div>
 )}
 </Card>
 );
}
