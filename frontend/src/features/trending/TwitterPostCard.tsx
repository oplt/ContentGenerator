import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Check, ExternalLink, Pencil, X } from "lucide-react";
import { postToTwitter } from "../../api/trending";
import { Button } from "../../components/ui/button";

export type TwitterPostCardProps = {
 repoId: string;
 initialText: string;
 onReject: () => void;
};

export function TwitterPostCard({ repoId, initialText, onReject }: TwitterPostCardProps) {
 const [editText, setEditText] = useState(initialText);
 const [editing, setEditing] = useState(false);
 const [postResult, setPostResult] = useState<{ url: string; dry: boolean } | null>(null);
 const [postError, setPostError] = useState<string | null>(null);

 const postMutation = useMutation({
 mutationFn: () => postToTwitter(repoId, editText),
 onSuccess: (data) => {
 setPostError(null);
 setPostResult({
 url: data.external_post_url,
 dry: data.status === "succeeded_dry_run",
 });
 },
 onError: (error) => {
 setPostError(error instanceof Error ? error.message : "Failed to post.");
 },
 });

 return (
 <div className="bg-muted p-4 flex flex-col gap-3" style={{ borderRadius: "var(--radius-sm)" }}>
 {editing ? (
 <textarea
 className="w-full text-sm text-foreground bg-background border border-border rounded p-2 resize-none focus:outline-none focus:ring-1 focus:ring-primary"
 rows={5}
 value={editText}
 onChange={(e) => setEditText(e.target.value)}
 />
 ) : (
 <p className="text-sm text-foreground whitespace-pre-wrap leading-relaxed">{editText}</p>
 )}

 <div className="flex items-center gap-2 flex-wrap">
 {postResult ? (
 <div className="flex items-center gap-2">
 <Check className="size-3.5 text-success" />
 <span className="text-xs text-success">
 {postResult.dry ? "Posted (dry run)" : "Posted!"}
 </span>
 {postResult.url && !postResult.dry && (
 <a
 href={postResult.url}
 target="_blank"
 rel="noopener noreferrer"
 className="text-xs text-primary underline flex items-center gap-1"
 >
 View <ExternalLink className="size-3" />
 </a>
 )}
 </div>
 ) : (
 <>
 <Button
 size="sm"
 variant="default"
 onClick={() => postMutation.mutate()}
 disabled={postMutation.isPending || editText.trim().length === 0}
 >
 <Check className="size-3.5" />
 {postMutation.isPending ? "Posting…" : "Accept & Post"}
 </Button>
 <Button size="sm" variant="secondary" onClick={() => setEditing((value) => !value)}>
 <Pencil className="size-3.5" />
 {editing ? "Done" : "Edit"}
 </Button>
 <Button size="sm" variant="ghost" onClick={onReject}>
 <X className="size-3.5" />
 Reject
 </Button>
 </>
 )}
 {postMutation.isError && (
 <p className="text-[11px] font-medium text-destructive">{postError}</p>
 )}
 </div>
 </div>
 );
}
