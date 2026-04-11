from __future__ import annotations

from fastapi.testclient import TestClient

import backend.api.main as main_module


def test_live_health_endpoint(monkeypatch):
    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(main_module.object_storage, "ensure_bucket", noop)
    monkeypatch.setattr(main_module, "bootstrap_application", noop)
    monkeypatch.setattr(main_module.redis_client, "aclose", noop)

    with TestClient(main_module.app) as client:
        response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
