from __future__ import annotations

from backend.modules.approvals.providers import StubWhatsAppProvider
from backend.modules.publishing.providers import StubPublishingProvider
from backend.modules.publishing.models import SocialAccount


async def test_stub_whatsapp_provider_parses_revise():
    provider = StubWhatsAppProvider()
    parsed = provider.parse_payload(
        {
            "approval_request_id": "d4ee4dd7-1412-4fc0-b20d-c57afd39c6ef",
            "text": "REVISE d4ee4dd7-1412-4fc0-b20d-c57afd39c6ef Make it tighter",
        }
    )[0]

    assert parsed.intent == "revise"
    assert parsed.feedback == "d4ee4dd7-1412-4fc0-b20d-c57afd39c6ef Make it tighter".split(" ", 1)[1]


async def test_stub_publishing_provider_returns_mock_url():
    provider = StubPublishingProvider("x")
    result = await provider.publish(
        social_account=SocialAccount(
            tenant_id="00000000-0000-0000-0000-000000000001",
            platform="x",
            display_name="Demo X",
            capability_flags={},
            account_metadata={"mode": "stub"},
        ),
        assets=[],
    )

    assert result.status == "succeeded"
    assert result.external_post_url is not None
