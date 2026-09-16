"""Phase 1 workflow domain models: brand↔account + automation bindings."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import Table, create_engine, event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from typing import cast

from backend.db.base import Base
from backend.modules.content_strategy.models import Brand, BrandSocialAccount
from backend.modules.identity_access.models import Tenant
from backend.modules.publishing.models import SocialAccount
from backend.modules.workflows.models import (
    Automation,
    AutomationTarget,
    AutomationTriggerType,
    WorkflowDefinition,
    WorkflowDefinitionStatus,
    WorkflowVersion,
)


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Stub users table: full User model has duplicate sqlite index defs.
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id CHAR(32) NOT NULL PRIMARY KEY)"))

    Base.metadata.create_all(
        engine,
        tables=cast(
            list[Table],
            [
                Tenant.__table__,
                Brand.__table__,
                SocialAccount.__table__,
                BrandSocialAccount.__table__,
                WorkflowDefinition.__table__,
                WorkflowVersion.__table__,
                Automation.__table__,
                AutomationTarget.__table__,
            ],
        ),
    )
    return sessionmaker(engine, expire_on_commit=False)()


def _seed_tenant_brand_accounts(db: Session) -> tuple[Tenant, Brand, SocialAccount, SocialAccount]:
    tenant = Tenant(name="Acme", slug=f"acme-{uuid.uuid4().hex[:8]}")
    db.add(tenant)
    db.flush()
    brand = Brand(tenant_id=tenant.id, name="Chess", niche="chess")
    x_account = SocialAccount(
        tenant_id=tenant.id,
        platform="x",
        display_name="Chess X",
        handle="@chess",
        account_external_id="x-chess-1",
    )
    yt_account = SocialAccount(
        tenant_id=tenant.id,
        platform="youtube",
        display_name="Chess YT",
        handle="ChessDaily",
        account_external_id="yt-chess-1",
    )
    db.add_all([brand, x_account, yt_account])
    db.flush()
    return tenant, brand, x_account, yt_account


def test_brand_can_own_multiple_social_accounts() -> None:
    db = _session()
    tenant, brand, x_account, yt_account = _seed_tenant_brand_accounts(db)

    db.add_all(
        [
            BrandSocialAccount(
                tenant_id=tenant.id,
                brand_id=brand.id,
                social_account_id=x_account.id,
            ),
            BrandSocialAccount(
                tenant_id=tenant.id,
                brand_id=brand.id,
                social_account_id=yt_account.id,
            ),
        ]
    )
    db.commit()

    links = (
        db.execute(
            select(BrandSocialAccount).where(
                BrandSocialAccount.tenant_id == tenant.id,
                BrandSocialAccount.brand_id == brand.id,
            )
        )
        .scalars()
        .all()
    )
    assert {link.social_account_id for link in links} == {x_account.id, yt_account.id}
    db.close()


def test_same_workflow_definition_binds_multiple_automations_and_brands() -> None:
    db = _session()
    tenant, chess_brand, x_account, yt_account = _seed_tenant_brand_accounts(db)
    tech_brand = Brand(tenant_id=tenant.id, name="Technology", niche="tech")
    db.add(tech_brand)
    db.flush()

    definition = WorkflowDefinition(
        tenant_id=tenant.id,
        name="Historical Chess Video",
        slug="historical-chess-video",
        status=WorkflowDefinitionStatus.ACTIVE.value,
    )
    db.add(definition)
    db.flush()

    version = WorkflowVersion(
        tenant_id=tenant.id,
        workflow_definition_id=definition.id,
        version=1,
        graph_json={"nodes": [], "edges": []},
        checksum="abc123",
    )
    db.add(version)
    db.flush()
    definition.current_version_id = version.id

    auto_chess = Automation(
        tenant_id=tenant.id,
        workflow_definition_id=definition.id,
        workflow_version_id=version.id,
        brand_id=chess_brand.id,
        name="Chess Daily",
        trigger_type=AutomationTriggerType.SCHEDULE.value,
        timezone="Europe/Brussels",
    )
    auto_tech = Automation(
        tenant_id=tenant.id,
        workflow_definition_id=definition.id,
        workflow_version_id=version.id,
        brand_id=tech_brand.id,
        name="Tech Remix",
        trigger_type=AutomationTriggerType.MANUAL.value,
    )
    db.add_all([auto_chess, auto_tech])
    db.flush()

    db.add_all(
        [
            AutomationTarget(
                tenant_id=tenant.id,
                automation_id=auto_chess.id,
                social_account_id=x_account.id,
            ),
            AutomationTarget(
                tenant_id=tenant.id,
                automation_id=auto_chess.id,
                social_account_id=yt_account.id,
            ),
            AutomationTarget(
                tenant_id=tenant.id,
                automation_id=auto_tech.id,
                social_account_id=x_account.id,
            ),
        ]
    )
    db.commit()

    autos = (
        db.execute(
            select(Automation).where(
                Automation.tenant_id == tenant.id,
                Automation.workflow_definition_id == definition.id,
            )
        )
        .scalars()
        .all()
    )
    assert len(autos) == 2
    assert {a.brand_id for a in autos} == {chess_brand.id, tech_brand.id}

    chess_targets = (
        db.execute(
            select(AutomationTarget).where(AutomationTarget.automation_id == auto_chess.id)
        )
        .scalars()
        .all()
    )
    tech_targets = (
        db.execute(
            select(AutomationTarget).where(AutomationTarget.automation_id == auto_tech.id)
        )
        .scalars()
        .all()
    )
    assert {t.social_account_id for t in chess_targets} == {x_account.id, yt_account.id}
    assert {t.social_account_id for t in tech_targets} == {x_account.id}
    db.close()


def test_duplicate_brand_social_account_rejected() -> None:
    db = _session()
    tenant, brand, x_account, _yt = _seed_tenant_brand_accounts(db)
    db.add(
        BrandSocialAccount(
            tenant_id=tenant.id,
            brand_id=brand.id,
            social_account_id=x_account.id,
        )
    )
    db.commit()

    db.add(
        BrandSocialAccount(
            tenant_id=tenant.id,
            brand_id=brand.id,
            social_account_id=x_account.id,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.close()


def test_cross_tenant_brand_social_account_rejected() -> None:
    db = _session()
    t1, brand, _x, _yt = _seed_tenant_brand_accounts(db)
    t2 = Tenant(name="Other", slug=f"other-{uuid.uuid4().hex[:8]}")
    db.add(t2)
    db.flush()
    foreign_account = SocialAccount(
        tenant_id=t2.id,
        platform="x",
        display_name="Foreign",
        account_external_id="x-foreign-1",
    )
    db.add(foreign_account)
    db.flush()

    db.add(
        BrandSocialAccount(
            tenant_id=t1.id,
            brand_id=brand.id,
            social_account_id=foreign_account.id,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.close()


def test_cross_tenant_automation_brand_rejected() -> None:
    db = _session()
    t1, brand, _x, _yt = _seed_tenant_brand_accounts(db)
    definition = WorkflowDefinition(
        tenant_id=t1.id,
        name="Shared Flow",
        slug="shared-flow",
    )
    db.add(definition)
    db.flush()
    version = WorkflowVersion(
        tenant_id=t1.id,
        workflow_definition_id=definition.id,
        version=1,
        graph_json={},
    )
    db.add(version)
    db.flush()

    t2 = Tenant(name="Other", slug=f"other-{uuid.uuid4().hex[:8]}")
    db.add(t2)
    db.flush()
    foreign_brand = Brand(tenant_id=t2.id, name="Foreign Brand", niche="other")
    db.add(foreign_brand)
    db.flush()

    db.add(
        Automation(
            tenant_id=t1.id,
            workflow_definition_id=definition.id,
            workflow_version_id=version.id,
            brand_id=foreign_brand.id,
            name="Bad bind",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.close()


def test_tenant_isolation_on_workflow_definitions() -> None:
    db = _session()
    t1 = Tenant(name="Alpha", slug=f"alpha-{uuid.uuid4().hex[:8]}")
    t2 = Tenant(name="Beta", slug=f"beta-{uuid.uuid4().hex[:8]}")
    db.add_all([t1, t2])
    db.flush()
    d1 = WorkflowDefinition(tenant_id=t1.id, name="A", slug="a")
    d2 = WorkflowDefinition(tenant_id=t2.id, name="B", slug="b")
    db.add_all([d1, d2])
    db.commit()

    listed = (
        db.execute(
            select(WorkflowDefinition).where(WorkflowDefinition.tenant_id == t1.id)
        )
        .scalars()
        .all()
    )
    assert len(listed) == 1
    assert listed[0].id == d1.id
    db.close()
