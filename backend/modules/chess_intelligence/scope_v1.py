"""§36 — do not overengineer chess v1.

Stay in the modular monolith. Prefer Postgres + Celery + existing storage /
providers / repos / API / frontend until observed scale demands more.
"""

from __future__ import annotations

# Must not appear as chess v1 dependencies or domain imports.
FORBIDDEN_V1_INFRA: frozenset[str] = frozenset(
    {
        "kafka",
        "aiokafka",
        "confluent_kafka",
        "elasticsearch",
        "opensearch",
        "opensearchpy",
        "clickhouse",
        "snowflake",
        "pulsar",
        "data_lake",
        "datalake",
    }
)

# Prefer these existing platform pieces (documentation / contract).
PREFERRED_STACK: tuple[str, ...] = (
    "PostgreSQL",
    "existing Celery",
    "existing object/file storage",
    "existing provider clients",
    "existing repositories",
    "existing API",
    "existing frontend",
)

ARCHITECTURE = "modular_monolith"


def chess_v1_stays_modular_monolith() -> bool:
    return ARCHITECTURE == "modular_monolith"


def forbidden_infra_tokens() -> frozenset[str]:
    return FORBIDDEN_V1_INFRA
