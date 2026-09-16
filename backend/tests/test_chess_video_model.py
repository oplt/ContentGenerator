"""Chess video job model + tenant isolation."""

from __future__ import annotations

import uuid
from typing import cast

from sqlalchemy import Table, create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.db.base import Base
from backend.modules.chess_video.models import ChessVideoJob, ChessVideoJobStatus
from backend.modules.identity_access.models import Tenant


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    # Avoid User table: duplicate index definitions break sqlite create_all.
    Base.metadata.create_all(
        engine,
        tables=cast(list[Table], [Tenant.__table__, ChessVideoJob.__table__]),
    )
    return sessionmaker(engine, expire_on_commit=False)()


def test_list_for_tenant_does_not_leak_other_tenant_jobs() -> None:
    db = _session()
    t1 = Tenant(name="Alpha", slug="alpha")
    t2 = Tenant(name="Beta", slug="beta")
    db.add_all([t1, t2])
    db.flush()

    job_a = ChessVideoJob(
        tenant_id=t1.id,
        source_text="1. e4 e5",
        status=ChessVideoJobStatus.QUEUED.value,
        stage=ChessVideoJobStatus.QUEUED.value,
    )
    job_b = ChessVideoJob(
        tenant_id=t2.id,
        source_text="1. d4 d5",
        status=ChessVideoJobStatus.QUEUED.value,
        stage=ChessVideoJobStatus.QUEUED.value,
    )
    db.add_all([job_a, job_b])
    db.commit()

    listed = (
        db.execute(
            select(ChessVideoJob)
            .where(ChessVideoJob.tenant_id == t1.id)
            .order_by(ChessVideoJob.created_at.desc())
        )
        .scalars()
        .all()
    )
    assert len(listed) == 1
    assert listed[0].id == job_a.id

    cross = db.execute(
        select(ChessVideoJob).where(
            ChessVideoJob.id == job_b.id,
            ChessVideoJob.tenant_id == t1.id,
        )
    ).scalar_one_or_none()
    assert cross is None
    assert len(db.execute(select(ChessVideoJob)).scalars().all()) == 2
    db.close()


def test_chess_video_job_stores_creator_and_tenant() -> None:
    db = _session()
    tenant = Tenant(name="Alpha", slug="alpha")
    db.add(tenant)
    db.flush()
    user_id = uuid.uuid4()

    job = ChessVideoJob(
        tenant_id=tenant.id,
        created_by_user_id=user_id,
        source_text="1. e4 e5 2. Nf3 Nc6",
        title="Demo",
    )
    db.add(job)
    db.commit()

    loaded = db.get(ChessVideoJob, job.id)
    assert loaded is not None
    assert loaded.tenant_id == tenant.id
    assert loaded.created_by_user_id == user_id
    assert loaded.title == "Demo"
    assert loaded.status == ChessVideoJobStatus.QUEUED.value
    db.close()
