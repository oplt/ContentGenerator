import { apiFetch } from "./client";

export type WorkerTaskSnapshot = {
  task_name: string;
  status: string;
  progress: number;
  started_at: string | null;
  finished_at: string | null;
};

export type WorkerQueueStatus = {
  queue_name: string;
  running: number;
  failed: number;
  completed: number;
  recent_tasks: WorkerTaskSnapshot[];
};

export type HealthReadiness = {
  status: string;
  checked_at: string;
  checks: Record<string, string>;
  inference_providers: Record<string, unknown>;
  inference_metrics: Record<string, unknown>;
  worker_status: WorkerQueueStatus[];
};

export function getHealthReadiness() {
  return apiFetch<HealthReadiness>("/health/ready");
}

export type AppConfig = {
  mfa_access: boolean;
};

export function getAppConfig() {
  return apiFetch<AppConfig>("/health/config");
}
