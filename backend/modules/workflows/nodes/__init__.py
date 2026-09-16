"""Workflow node package exports (no registry import — avoids cycles)."""

from __future__ import annotations

from backend.modules.workflows.nodes.analytics import FetchMetricsNode
from backend.modules.workflows.nodes.approval import ApprovalNode
from backend.modules.workflows.nodes.audio import GenerateTTSNode
from backend.modules.workflows.nodes.chess import GenerateChessVideoNode
from backend.modules.workflows.nodes.control import (
    ConditionNode,
    DelayNode,
    FanOutNode,
    MergeNode,
    WaitNode,
)
from backend.modules.workflows.nodes.fact_review import FactReviewNode
from backend.modules.workflows.nodes.image import GenerateImageNode
from backend.modules.workflows.nodes.platform_transform import PlatformTransformNode
from backend.modules.workflows.nodes.publishing import PublishNode
from backend.modules.workflows.nodes.research import ResearchSourcesNode
from backend.modules.workflows.nodes.text import (
    GenerateScriptNode,
    GenerateTextNode,
    SummarizeNode,
)
from backend.modules.workflows.nodes.triggers import (
    ManualTriggerNode,
    ScheduleTriggerNode,
    WebhookTriggerNode,
)
from backend.modules.workflows.nodes.video import GenerateVideoNode

IMPLEMENTED_SLICE = (
    ManualTriggerNode,
    GenerateTextNode,
    SummarizeNode,
    GenerateScriptNode,
    FactReviewNode,
    GenerateImageNode,
    GenerateTTSNode,
    GenerateVideoNode,
    GenerateChessVideoNode,
    ConditionNode,
    FanOutNode,
    MergeNode,
    WaitNode,
    DelayNode,
    PlatformTransformNode,
    ApprovalNode,
    PublishNode,
)

ALL_NODE_TYPES = (
    ManualTriggerNode,
    ScheduleTriggerNode,
    WebhookTriggerNode,
    ResearchSourcesNode,
    GenerateTextNode,
    SummarizeNode,
    GenerateScriptNode,
    FactReviewNode,
    GenerateImageNode,
    GenerateTTSNode,
    GenerateVideoNode,
    GenerateChessVideoNode,
    ApprovalNode,
    ConditionNode,
    FanOutNode,
    MergeNode,
    WaitNode,
    DelayNode,
    PlatformTransformNode,
    PublishNode,
    FetchMetricsNode,
)

__all__ = [
    "ALL_NODE_TYPES",
    "IMPLEMENTED_SLICE",
]
