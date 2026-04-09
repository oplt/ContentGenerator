# Editorial Workflow

SignalForge operates as a semi-autonomous editorial system with mandatory human approvals.

## Canonical workflow

1. Signal ingestion
2. Normalization and deduplication
3. Trend candidate scoring
4. Editorial brief generation
5. Telegram approval for topic/brief
6. Asset package generation
7. Telegram approval for assets/publish
8. Publish job execution
9. Analytics collection and feedback

## Primary persistent objects

- `Source`
- `RawArticle`
- `NormalizedArticle`
- `StoryCluster` as the current trend-candidate persistence layer
- `EditorialBrief`
- `ApprovalRequest`
- `GeneratedAsset`
- `PublishingJob`
- `PublishedPost`
- analytics snapshots and optimization aggregates

## Workflow state mapping

The current repository uses `StoryCluster.workflow_state` to represent the top-level editorial state machine:

- `new`
- `queued_for_review`
- `approved_topic`
- `brief_ready`
- `asset_generation`
- `asset_review`
- `publish_ready`
- `published`
- `rejected`
- `expired`

This keeps the repo aligned with a single editorial pipeline even where some internal table names still use older “story cluster” terminology for compatibility.

## Approval model

Telegram is the primary approval channel.

Approval stages:

1. Topic / brief approval
2. Asset approval
3. Publish approval

WhatsApp remains a legacy fallback transport only.

## Compatibility note

Some legacy routes and model names still use `stories`, `story_clusters`, and `content_jobs`. These remain supported to avoid breaking existing flows, but the product should be understood and documented as:

`trend candidates -> editorial briefs -> asset packages -> publish jobs -> analytics`
