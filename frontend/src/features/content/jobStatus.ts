export const JOB_STATUS_VARIANT: Record<string, "default" | "success" | "warning" | "muted"> = {
  pending: "muted",
  running: "warning",
  completed: "success",
  failed: "warning",
};
