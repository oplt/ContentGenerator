import type { Period } from "../../api/trending";

export const PERIOD_LABELS: Record<Period, string> = {
  daily: "Today",
  weekly: "This Week",
  monthly: "This Month",
};

export const PERIODS = ["daily", "weekly", "monthly"] as const;
