from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass
class InferenceMetrics:
    structured_parse_failures: Counter[tuple[str, str]] = field(default_factory=Counter)
    structured_recoveries: Counter[tuple[str, str]] = field(default_factory=Counter)
    provider_failures: Counter[tuple[str, str]] = field(default_factory=Counter)

    def record_parse_failure(self, provider_name: str, task: str) -> None:
        self.structured_parse_failures[(provider_name, task)] += 1
        try:
            from backend.core.domain_metrics import domain_metrics

            domain_metrics.record_inference_event(provider=provider_name, event="parse_failure")
        except Exception:
            pass

    def record_recovery(self, provider_name: str, task: str) -> None:
        self.structured_recoveries[(provider_name, task)] += 1
        try:
            from backend.core.domain_metrics import domain_metrics

            domain_metrics.record_inference_event(provider=provider_name, event="recovery")
        except Exception:
            pass

    def record_provider_failure(self, provider_name: str, task: str) -> None:
        self.provider_failures[(provider_name, task)] += 1
        try:
            from backend.core.domain_metrics import domain_metrics

            domain_metrics.record_inference_event(provider=provider_name, event="provider_failure")
        except Exception:
            pass

    def snapshot(self) -> dict[str, dict[str, int]]:
        def _flatten(counter: Counter[tuple[str, str]]) -> dict[str, int]:
            return {f"{provider}:{task}": count for (provider, task), count in sorted(counter.items())}

        return {
            "structured_parse_failures": _flatten(self.structured_parse_failures),
            "structured_recoveries": _flatten(self.structured_recoveries),
            "provider_failures": _flatten(self.provider_failures),
        }


inference_metrics = InferenceMetrics()


def get_inference_metrics_snapshot() -> dict[str, dict[str, int]]:
    return inference_metrics.snapshot()
