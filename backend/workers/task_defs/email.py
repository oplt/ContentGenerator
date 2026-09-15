from __future__ import annotations

from backend.workers.email import send_email_sync
from backend.workers.task_defs._common import task as _task


@_task("backend.workers.tasks.send_email_task")
def send_email_task(*, to: str, subject: str, html_body: str, text_body: str | None = None) -> None:
    send_email_sync(to=to, subject=subject, html_body=html_body, text_body=text_body)
