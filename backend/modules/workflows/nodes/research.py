"""Research / source nodes (stubs until later phases)."""

from __future__ import annotations

from backend.modules.workflows.nodes.base import make_stub_node

ResearchSourcesNode = make_stub_node(
    node_type="research_sources",
    category="sources",
    display_name="Research Sources",
    description="Fetch/cluster research inputs via source ingestion + story intelligence.",
)
