from __future__ import annotations

from backend.workers.email import queue_email
from backend.workers.tasks import send_email_task


def test_send_email_task_invokes_sender(monkeypatch):
    captured: dict[str, str] = {}

    def fake_send_email_sync(*, to: str, subject: str, html_body: str, text_body: str | None = None):
        captured["to"] = to
        captured["subject"] = subject
        captured["html_body"] = html_body

    monkeypatch.setattr("backend.workers.tasks.send_email_sync", fake_send_email_sync)
    send_email_task(to="test@example.com", subject="Hello", html_body="<p>Hi</p>")

    assert captured["to"] == "test@example.com"


def test_queue_email_uses_configured_email_queue(monkeypatch):
    captured: dict[str, object] = {}

    class DummyTask:
        def apply_async(self, *, kwargs: dict[str, str | None], queue: str) -> None:
            captured["kwargs"] = kwargs
            captured["queue"] = queue

    monkeypatch.setattr("backend.workers.tasks.send_email_task", DummyTask())
    monkeypatch.setattr("backend.workers.email.settings.CELERY_TASK_ALWAYS_EAGER", False)
    monkeypatch.setattr("backend.workers.email.settings.CELERY_QUEUE_EMAIL", "email")

    queue_email(to="test@example.com", subject="Hello", html_body="<p>Hi</p>")

    assert captured["queue"] == "email"
    assert captured["kwargs"] == {
        "to": "test@example.com",
        "subject": "Hello",
        "html_body": "<p>Hi</p>",
        "text_body": None,
    }
