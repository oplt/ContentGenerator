"""Analytics nodes (stubs)."""

from __future__ import annotations

from backend.modules.workflows.nodes.base import make_stub_node

FetchMetricsNode = make_stub_node(
    node_type="fetch_metrics",
    category="analytics",
    display_name="Fetch Metrics",
    description="Pull post/account metrics via analytics services.",
)
