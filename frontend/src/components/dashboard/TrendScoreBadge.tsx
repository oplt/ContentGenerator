import { Badge } from "../ui/badge";

export function TrendScoreBadge({ score }: { score: number | null }) {
  if (score == null) {
    return <Badge variant="muted">No score</Badge>;
  }
  const variant = score >= 0.75 ? "success" : score >= 0.55 ? "warning" : "muted";
  return <Badge variant={variant}>{score.toFixed(2)}</Badge>;
}
