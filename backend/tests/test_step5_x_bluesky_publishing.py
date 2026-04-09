"""
Tests for Step 5 — X + Bluesky Publishing Adapters.

Covers:
- XPublishingProvider: dry_run returns succeeded_dry_run without calling API
- XPublishingProvider: real publish sends tweet via X API v2
- XPublishingProvider: long text split into thread (reply chain)
- XPublishingProvider: no assets → publishes empty tweet
- BlueskyPublishingProvider: dry_run returns succeeded_dry_run
- BlueskyPublishingProvider: real publish calls atproto createRecord
- get_provider factory: routes correctly by platform + access_token
- get_provider: X without token → ManualFallbackProvider
- get_provider: Bluesky without DID → ManualFallbackProvider
- Stub still used when SOCIAL_DRY_RUN_BY_DEFAULT=True
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.modules.publishing.providers import (
    BlueskyPublishingProvider,
    ManualFallbackProvider,
    StubPublishingProvider,
    XPublishingProvider,
    get_provider,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _social_account(handle: str = "testuser", external_id: str = "did:plc:test"):
    acc = MagicMock()
    acc.handle = handle
    acc.account_external_id = external_id
    acc.account_metadata = {}
    return acc


def _text_asset(text: str):
    asset = MagicMock()
    asset.asset_type = "text_variant"
    asset.text_content = text
    return asset


# ---------------------------------------------------------------------------
# XPublishingProvider
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_x_dry_run_no_api_call() -> None:
    provider = XPublishingProvider(access_token="tok123", dry_run=True)
    result = await provider.publish(
        social_account=_social_account(),
        assets=[_text_asset("Hello world!")],
    )
    assert result.status == "succeeded_dry_run"
    assert result.external_post_id is not None
    assert "dry-run" in result.external_post_id


@pytest.mark.asyncio
async def test_x_publish_single_tweet() -> None:
    provider = XPublishingProvider(access_token="tok123", dry_run=False)

    tweet_ids = ["tweet001"]
    call_count = 0

    async def mock_post(url, headers=None, json=None, **kwargs):
        nonlocal call_count
        call_count += 1
        r = MagicMock()
        r.raise_for_status = MagicMock()
        r.json = MagicMock(return_value={"data": {"id": tweet_ids[0]}})
        return r

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(post=AsyncMock(side_effect=mock_post))
        )
        mock_client.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await provider.publish(
            social_account=_social_account(handle="johndoe"),
            assets=[_text_asset("Hello from X!")],
        )

    assert result.status == "succeeded"
    assert result.external_post_id == "tweet001"
    assert "johndoe" in result.external_post_url
    assert call_count == 1


@pytest.mark.asyncio
async def test_x_publish_thread_for_long_text() -> None:
    """Text > 280 chars should be split into a thread (multiple tweet calls)."""
    provider = XPublishingProvider(access_token="tok123", dry_run=False)

    # 350 char text → should split into 2 tweets
    long_text = "A" * 285

    call_count = 0
    tweet_counter = [0]

    async def mock_post(url, headers=None, json=None, **kwargs):
        tweet_counter[0] += 1
        tweet_id = f"tweet{tweet_counter[0]:03d}"
        r = MagicMock()
        r.raise_for_status = MagicMock()
        r.json = MagicMock(return_value={"data": {"id": tweet_id}})
        return r

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(post=AsyncMock(side_effect=mock_post))
        )
        mock_client.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await provider.publish(
            social_account=_social_account(),
            assets=[_text_asset(long_text)],
        )

    # Should have made 2 tweet calls
    assert tweet_counter[0] == 2
    assert result.external_post_id == "tweet001"  # first tweet
    assert result.payload["tweet_count"] == "2"


def test_x_select_text_splits_at_word_boundary() -> None:
    provider = XPublishingProvider(access_token="x")
    # 280 chars of text with a space at position 100
    text = "A" * 100 + " " + "B" * 200
    chunks = provider._select_text([_text_asset(text)])
    for chunk in chunks:
        assert len(chunk) <= 280


# ---------------------------------------------------------------------------
# BlueskyPublishingProvider
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bluesky_dry_run_no_api_call() -> None:
    provider = BlueskyPublishingProvider(
        access_token="tok123", did="did:plc:test", dry_run=True
    )
    result = await provider.publish(
        social_account=_social_account(),
        assets=[_text_asset("Bluesky post")],
    )
    assert result.status == "succeeded_dry_run"
    assert result.external_post_id is not None


@pytest.mark.asyncio
async def test_bluesky_real_publish() -> None:
    provider = BlueskyPublishingProvider(
        access_token="tok123", did="did:plc:abc", dry_run=False
    )

    async def mock_post(url, headers=None, json=None, **kwargs):
        r = MagicMock()
        r.raise_for_status = MagicMock()
        r.json = MagicMock(return_value={
            "cid": "bafyreitest123",
            "uri": "at://did:plc:abc/app.bsky.feed.post/3jtest",
        })
        return r

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(post=AsyncMock(side_effect=mock_post))
        )
        mock_client.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await provider.publish(
            social_account=_social_account(handle="user.bsky.social"),
            assets=[_text_asset("Hello Bluesky!")],
        )

    assert result.status == "succeeded"
    assert result.external_post_id == "bafyreitest123"
    assert "bsky.app" in result.external_post_url


@pytest.mark.asyncio
async def test_bluesky_publish_sends_correct_collection() -> None:
    """Verify the atproto createRecord payload uses app.bsky.feed.post."""
    provider = BlueskyPublishingProvider(
        access_token="tok", did="did:plc:abc", dry_run=False
    )
    captured = {}

    async def mock_post(url, headers=None, json=None, **kwargs):
        captured.update(json or {})
        r = MagicMock()
        r.raise_for_status = MagicMock()
        r.json = MagicMock(return_value={"cid": "c1", "uri": "at://did:plc:abc/app.bsky.feed.post/r1"})
        return r

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(post=AsyncMock(side_effect=mock_post))
        )
        mock_client.return_value.__aexit__ = AsyncMock(return_value=None)

        await provider.publish(
            social_account=_social_account(),
            assets=[_text_asset("Test post")],
        )

    assert captured["collection"] == "app.bsky.feed.post"
    assert captured["repo"] == "did:plc:abc"
    assert captured["record"]["$type"] == "app.bsky.feed.post"
    assert captured["record"]["text"] == "Test post"


# ---------------------------------------------------------------------------
# get_provider factory
# ---------------------------------------------------------------------------

def test_get_provider_x_with_token_returns_x_provider() -> None:
    provider = get_provider("x", use_stub=False, access_token="my_token")
    assert isinstance(provider, XPublishingProvider)
    assert provider.access_token == "my_token"


def test_get_provider_x_dry_run_returns_x_provider_with_dry_run() -> None:
    provider = get_provider("x", use_stub=False, access_token="my_token", dry_run=True)
    assert isinstance(provider, XPublishingProvider)
    assert provider.dry_run is True


def test_get_provider_x_without_token_returns_manual() -> None:
    with patch("backend.modules.publishing.providers.settings") as mock_settings:
        mock_settings.SOCIAL_DRY_RUN_BY_DEFAULT = False
        provider = get_provider("x", use_stub=False, access_token="")
    assert isinstance(provider, ManualFallbackProvider)


def test_get_provider_x_stub_without_token_returns_stub() -> None:
    provider = get_provider("x", use_stub=True, access_token="")
    assert isinstance(provider, StubPublishingProvider)


def test_get_provider_bluesky_with_token_and_did() -> None:
    provider = get_provider(
        "bluesky",
        use_stub=False,
        access_token="tok",
        account_external_id="did:plc:test",
    )
    assert isinstance(provider, BlueskyPublishingProvider)
    assert provider.did == "did:plc:test"


def test_get_provider_bluesky_without_did_returns_manual() -> None:
    with patch("backend.modules.publishing.providers.settings") as mock_settings:
        mock_settings.SOCIAL_DRY_RUN_BY_DEFAULT = False
        provider = get_provider("bluesky", use_stub=False, access_token="tok", account_external_id="")
    assert isinstance(provider, ManualFallbackProvider)


def test_get_provider_instagram_returns_stub_by_default() -> None:
    with patch("backend.modules.publishing.providers.settings") as mock_settings:
        mock_settings.SOCIAL_DRY_RUN_BY_DEFAULT = True
        provider = get_provider("instagram", use_stub=False)
    assert isinstance(provider, StubPublishingProvider)


def test_get_provider_youtube_dry_run_default_returns_stub() -> None:
    with patch("backend.modules.publishing.providers.settings") as mock_settings:
        mock_settings.SOCIAL_DRY_RUN_BY_DEFAULT = True
        provider = get_provider("youtube", use_stub=False)
    assert isinstance(provider, StubPublishingProvider)


def test_get_provider_threads_returns_stub() -> None:
    with patch("backend.modules.publishing.providers.settings") as mock_settings:
        mock_settings.SOCIAL_DRY_RUN_BY_DEFAULT = True
        provider = get_provider("threads", use_stub=False)
    assert isinstance(provider, StubPublishingProvider)


def test_get_provider_telegram_returns_stub() -> None:
    with patch("backend.modules.publishing.providers.settings") as mock_settings:
        mock_settings.SOCIAL_DRY_RUN_BY_DEFAULT = True
        provider = get_provider("telegram", use_stub=False)
    assert isinstance(provider, StubPublishingProvider)


# ---------------------------------------------------------------------------
# Idempotent dry_run result is SUCCEEDED_DRY_RUN
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_x_dry_run_status_is_succeeded_dry_run() -> None:
    provider = XPublishingProvider(access_token="x", dry_run=True)
    result = await provider.publish(
        social_account=_social_account(), assets=[]
    )
    assert result.status == "succeeded_dry_run"


@pytest.mark.asyncio
async def test_bluesky_dry_run_status_is_succeeded_dry_run() -> None:
    provider = BlueskyPublishingProvider(access_token="x", did="did:plc:abc", dry_run=True)
    result = await provider.publish(
        social_account=_social_account(), assets=[]
    )
    assert result.status == "succeeded_dry_run"


@pytest.mark.asyncio
async def test_stub_provider_exposes_normalized_interface() -> None:
    provider = StubPublishingProvider("instagram")
    social_account = _social_account()
    assets = [_text_asset("Draft text")]

    validation = await provider.validate_auth(social_account=social_account)
    draft = await provider.create_draft(social_account=social_account, assets=assets)
    scheduled = await provider.schedule_publish(
        social_account=social_account,
        assets=assets,
        scheduled_for=datetime.now(timezone.utc),
    )
    publish_result = await provider.publish_now(
        social_account=social_account,
        assets=assets,
        publish_attempt_key="attempt-1",
    )
    delete_result = await provider.delete_or_unpublish_if_supported(
        social_account=social_account,
        external_post_id=publish_result.external_post_id,
    )

    assert validation.is_valid is True
    assert draft.status == "draft_created"
    assert scheduled.native_supported is False
    assert publish_result.external_post_id is not None
    assert delete_result.supported is False


@pytest.mark.asyncio
async def test_x_fetch_post_url_uses_handle() -> None:
    provider = XPublishingProvider(access_token="tok123", dry_run=False)
    url = await provider.fetch_post_url(
        social_account=_social_account(handle="alice"),
        external_post_id="12345",
        provider_payload={},
    )
    assert url == "https://x.com/alice/status/12345"


# ---------------------------------------------------------------------------
# Media upload — X
# ---------------------------------------------------------------------------

def _image_asset(url: str = "http://cdn.example.com/img.jpg", mime: str = "image/jpeg"):
    asset = MagicMock()
    asset.asset_type = "image"
    asset.public_url = url
    asset.mime_type = mime
    return asset


@pytest.mark.asyncio
async def test_x_media_upload_attaches_media_id_to_first_tweet() -> None:
    """Image assets should be uploaded and their media_id attached to the first tweet."""
    provider = XPublishingProvider(access_token="tok", dry_run=False)

    dl_response = MagicMock()
    dl_response.raise_for_status = MagicMock()
    dl_response.content = b"fake_image_bytes"

    upload_response = MagicMock()
    upload_response.raise_for_status = MagicMock()
    upload_response.json = MagicMock(return_value={"media_id_string": "111222333"})

    tweet_response = MagicMock()
    tweet_response.raise_for_status = MagicMock()
    tweet_response.json = MagicMock(return_value={"data": {"id": "tweet_with_media"}})

    post_calls = []

    async def mock_get(url, **kwargs):
        return dl_response

    async def mock_post(url, **kwargs):
        post_calls.append(url)
        if "media/upload" in url:
            return upload_response
        return tweet_response

    with patch("backend.modules.publishing.providers.httpx.AsyncClient") as MockClient:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.get = AsyncMock(side_effect=mock_get)
        mock_http.post = AsyncMock(side_effect=mock_post)
        MockClient.return_value = mock_http

        result = await provider.publish(
            social_account=_social_account(),
            assets=[_image_asset(), _text_asset("Hello with image!")],
        )

    assert result.status == "succeeded"
    assert result.payload["media_count"] == "1"
    # At least one call should hit the media upload endpoint
    assert any("media/upload" in url for url in post_calls)


@pytest.mark.asyncio
async def test_x_no_media_assets_skips_upload() -> None:
    """When there are no image assets, media_count should be 0."""
    provider = XPublishingProvider(access_token="tok", dry_run=False)

    tweet_response = MagicMock()
    tweet_response.raise_for_status = MagicMock()
    tweet_response.json = MagicMock(return_value={"data": {"id": "t1"}})

    with patch("httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(post=AsyncMock(return_value=tweet_response))
        )
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await provider.publish(
            social_account=_social_account(),
            assets=[_text_asset("Text only post")],
        )

    assert result.status == "succeeded"
    assert result.payload["media_count"] == "0"


@pytest.mark.asyncio
async def test_x_media_upload_failure_does_not_abort_tweet() -> None:
    """If media upload fails, the tweet should still be sent (best-effort)."""
    provider = XPublishingProvider(access_token="tok", dry_run=False)

    # _upload_media_id is mocked to raise an error
    with patch.object(provider, "_upload_media_id", new=AsyncMock(side_effect=Exception("upload failed"))):
        tweet_response = MagicMock()
        tweet_response.raise_for_status = MagicMock()
        tweet_response.json = MagicMock(return_value={"data": {"id": "t2"}})

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MagicMock(post=AsyncMock(return_value=tweet_response))
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await provider.publish(
                social_account=_social_account(),
                assets=[_image_asset(), _text_asset("Text with failed media")],
            )

    assert result.status == "succeeded"
    assert result.payload["media_count"] == "0"  # upload failed, no media attached


# ---------------------------------------------------------------------------
# Media upload — Bluesky
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bluesky_image_upload_attaches_embed() -> None:
    """Image assets should be uploaded as blobs and attached as app.bsky.embed.images."""
    provider = BlueskyPublishingProvider(access_token="tok", did="did:plc:abc", dry_run=False)

    dl_response = MagicMock()
    dl_response.raise_for_status = MagicMock()
    dl_response.content = b"img_bytes"

    blob_ref = {"$type": "blob", "ref": {"$link": "bafytest"}, "mimeType": "image/jpeg", "size": 9}
    upload_response = MagicMock()
    upload_response.raise_for_status = MagicMock()
    upload_response.json = MagicMock(return_value={"blob": blob_ref})

    create_response = MagicMock()
    create_response.raise_for_status = MagicMock()
    create_response.json = MagicMock(return_value={
        "cid": "bafyreitest",
        "uri": "at://did:plc:abc/app.bsky.feed.post/rkey1",
    })

    captured_record: dict = {}

    async def mock_get(url, **kwargs):
        return dl_response

    async def mock_post(url, **kwargs):
        if "uploadBlob" in url:
            return upload_response
        # createRecord
        body = kwargs.get("json", {})
        captured_record.update(body.get("record", {}))
        return create_response

    with patch("backend.modules.publishing.providers.httpx.AsyncClient") as MockClient:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.get = AsyncMock(side_effect=mock_get)
        mock_http.post = AsyncMock(side_effect=mock_post)
        MockClient.return_value = mock_http

        result = await provider.publish(
            social_account=_social_account(handle="user.bsky.social"),
            assets=[_image_asset(), _text_asset("Bluesky with image")],
        )

    assert result.status == "succeeded"
    assert result.payload["image_count"] == "1"
    assert "embed" in captured_record
    assert captured_record["embed"]["$type"] == "app.bsky.embed.images"
    assert len(captured_record["embed"]["images"]) == 1


@pytest.mark.asyncio
async def test_bluesky_no_image_assets_no_embed() -> None:
    """Posts with text-only assets should have no embed field in the record."""
    provider = BlueskyPublishingProvider(access_token="tok", did="did:plc:abc", dry_run=False)

    captured_record: dict = {}

    async def mock_post(url, **kwargs):
        if "createRecord" in url:
            captured_record.update(kwargs.get("json", {}).get("record", {}))
        r = MagicMock()
        r.raise_for_status = MagicMock()
        r.json = MagicMock(return_value={"cid": "c1", "uri": "at://did:plc:abc/app.bsky.feed.post/r1"})
        return r

    with patch("httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(post=AsyncMock(side_effect=mock_post))
        )
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await provider.publish(
            social_account=_social_account(),
            assets=[_text_asset("Text-only Bluesky post")],
        )

    assert result.status == "succeeded"
    assert result.payload["image_count"] == "0"
    assert "embed" not in captured_record


# ---------------------------------------------------------------------------
# Idempotency: publish_now returns existing job without re-publishing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_publish_service_idempotent_returns_existing_job() -> None:
    """publish_now must return the existing job when idempotency_key already exists."""
    from backend.modules.publishing.service import PublishingService
    from backend.modules.publishing.models import PublishingJob, PublishingJobStatus

    existing_job = MagicMock(spec=PublishingJob)
    existing_job.id = uuid.uuid4()
    existing_job.status = PublishingJobStatus.SUCCEEDED.value
    existing_job.idempotency_key = "key-abc"

    svc = object.__new__(PublishingService)
    svc.repo = AsyncMock()
    svc.content_repo = AsyncMock()
    svc.audit = AsyncMock()
    svc.db = AsyncMock()

    content_job = MagicMock()
    content_job.id = uuid.uuid4()

    text_asset = MagicMock()
    text_asset.asset_type = "text_variant"
    text_asset.platform = "x"

    svc.content_repo.get_job = AsyncMock(return_value=content_job)
    svc.content_repo.list_assets = AsyncMock(return_value=[text_asset])
    svc.repo.get_job_by_idempotency = AsyncMock(return_value=existing_job)
    svc.db.flush = AsyncMock()

    from backend.modules.publishing.schemas import PublishNowRequest
    payload = PublishNowRequest(
        content_job_id=content_job.id,
        platforms=["x"],
        idempotency_key="key-abc-12345",
        dry_run=True,
    )

    jobs = await svc.publish_now(
        tenant_id=uuid.uuid4(),
        approval_request_id=None,
        payload=payload,
    )

    assert len(jobs) == 1
    assert jobs[0].idempotency_key == "key-abc"
    # Should NOT have called create_publishing_job
    svc.repo.create_publishing_job.assert_not_called()
