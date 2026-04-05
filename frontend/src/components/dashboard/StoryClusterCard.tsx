import { Link } from "react-router-dom";
import type { StoryCluster } from "../../api/stories";
import { Card } from "../ui/card";
import { Badge } from "../ui/badge";
import { TrendScoreBadge } from "./TrendScoreBadge";

export function StoryClusterCard({ cluster }: { cluster: StoryCluster }) {
  return (
    <Link to={`/dashboard/stories/${cluster.id}`}>
      <Card className="group h-full p-5 transition hover:border-primary/40">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{cluster.primary_topic}</p>
            <h3 className="mt-2 text-lg font-semibold leading-tight">{cluster.headline}</h3>
          </div>
          <TrendScoreBadge score={cluster.latest_trend_score} />
        </div>
        <p className="mt-3 text-sm text-muted-foreground">{cluster.summary}</p>
        <div className="mt-4 flex items-center gap-2">
          <Badge variant={cluster.worthy_for_content ? "success" : "muted"}>
            {cluster.worthy_for_content ? "Generate" : "Hold"}
          </Badge>
          <Badge variant={cluster.risk_level === "safe" ? "default" : "warning"}>
            {cluster.risk_level}
          </Badge>
        </div>
      </Card>
    </Link>
  );
}
